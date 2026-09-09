#!/usr/bin/env python3
"""Capture the Motivue serial log to a text file.

Written for one job: sitting in a car with a laptop, running the OBD probe,
and coming away with a file that can be read later. So it optimises for not
losing data rather than for features.

  - Every line is flushed to disk as it arrives. A knocked USB cable costs you
    the rest of the session, never the part you already captured.
  - ANSI colour codes are stripped, because ESP-IDF's log colouring turns a
    text file into unreadable escape soup.
  - The probe report is extracted into its own file alongside the full log,
    since that is the part worth sending to someone.
  - Keys typed here are forwarded to the board, so the interface can be driven
    while the session is being captured:

        a / h  left     d / l  right     o / Enter  select     b / q  back

Usage:
    python3 tools/capture.py                    # auto-detect the port
    python3 tools/capture.py -p /dev/ttyACM0
    python3 tools/capture.py -o lancer-2007     # name the capture

Needs pyserial. If this shell does not have it, the script re-runs itself
with the ESP-IDF virtualenv's Python, which does - so there is nothing to
source first.
"""

import argparse
import datetime
import glob
import os
import re
import select
import sys
import threading

def _find_python_with_pyserial():
    """Locate an interpreter that has pyserial, without needing export.sh.

    ESP-IDF keeps one in its virtualenv. Sitting in a car is the wrong moment
    to discover you forgot to source a shell script, so we go and find it.
    """
    import subprocess
    # Compared as written, not resolved: a virtualenv's bin/python is usually
    # a symlink to the very interpreter we are already running. It is the path
    # used to launch it that activates the environment, so resolving symlinks
    # here would discard exactly the candidate we are looking for.
    for pattern in ("~/.espressif/python_env/*/bin/python",
                    "~/esp/esp-idf/python_env/*/bin/python"):
        for cand in sorted(glob.glob(os.path.expanduser(pattern)), reverse=True):
            if cand == sys.executable:
                continue
            try:
                subprocess.run([cand, "-c", "import serial"], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15)
            except Exception:
                continue
            return cand
    return None


try:
    import serial
except ImportError:
    # The guard stops a re-exec loop if the interpreter we pick is also missing
    # pyserial for some reason we did not anticipate.
    if not os.environ.get("MV_CAPTURE_REEXEC"):
        _py = _find_python_with_pyserial()
        if _py:
            os.environ["MV_CAPTURE_REEXEC"] = "1"
            os.execv(_py, [_py, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit("pyserial not found, and no ESP-IDF Python has it either.\n"
             "Install it with:  pip install --user pyserial\n"
             "or source the IDF environment:  . $HOME/esp/esp-idf/export.sh")

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# The probe prefixes every one of its lines with this tag.
PROBE_LINE = re.compile(r"probe: \| ?(.*)$")
PROBE_START = "======== MOTIVUE OBD PROBE ========"
PROBE_END = "======== END OF PROBE ========"


# USB-serial bridges we expect to be looking at, most specific first.
# The DevKit in this project uses a WCH CH9102, which enumerates as CDC-ACM.
KNOWN_BRIDGES = {
    (0x1A86, 0x55D4): "WCH CH9102 (this project's DevKit)",
    (0x1A86, 0x7523): "WCH CH340",
    (0x10C4, 0xEA60): "Silicon Labs CP210x",
    (0x0403, 0x6001): "FTDI FT232",
}


def list_ports():
    """Every serial port the system reports, best candidate first.

    Uses pyserial's enumeration rather than globbing /dev, because the same
    board appears under a different name on each OS: /dev/ttyACM0 on Linux,
    /dev/cu.usbmodem* on macOS, COM3 on Windows. Globbing for one spelling is
    how a plugged-in board gets reported as missing.
    """
    try:
        from serial.tools import list_ports as lp
        ports = list(lp.comports())
    except Exception:
        ports = []

    def rank(p):
        vid = getattr(p, "vid", None)
        pid = getattr(p, "pid", None)
        if (vid, pid) in KNOWN_BRIDGES:
            return 0                      # exactly what we are looking for
        if vid is not None:
            return 1                      # some other USB serial device
        return 2                          # built-in port, almost never it

    ports.sort(key=rank)
    # A machine with no pyserial enumeration at all still gets a chance.
    if not ports:
        names = []
        for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.usbmodem*",
                        "/dev/cu.usbserial*", "/dev/cu.wchusbserial*"):
            names += sorted(glob.glob(pattern))
        return [(n, "found by name", True) for n in names]

    out = []
    for p in ports:
        vid, pid = getattr(p, "vid", None), getattr(p, "pid", None)
        if (vid, pid) in KNOWN_BRIDGES:
            label, usb = KNOWN_BRIDGES[(vid, pid)], True
        elif vid is not None:
            label, usb = f"{p.description} [{vid:04x}:{pid:04x}]", True
        else:
            label, usb = (p.description or "built-in serial port"), False
        out.append((p.device, label, usb))
    return out


def find_port():
    """Auto-select only a USB device.

    Never a built-in port: most PCs expose a motherboard /dev/ttyS0 with
    nothing attached, and opening it fails in a way that looks like a broken
    tool rather than a missing board.
    """
    for dev, _label, usb in list_ports():
        if usb:
            return dev
    return None


def no_port_message():
    """Say what the machine actually reported, not just that nothing was found.

    "No serial port found" on its own is the least useful thing a tool can
    say, because it cannot be told apart from a cable fault, a permissions
    problem, or a missing driver.
    """
    seen = list_ports()
    usb = [(d, l) for d, l, is_usb in seen if is_usb]
    builtin = [d for d, _l, is_usb in seen if not is_usb]

    lines = ["No USB serial device found - the board is not reaching this laptop."]

    if usb:
        lines += ["", "USB serial devices seen:"]
        lines += [f"    {d}    {l}" for d, l in usb]
        lines += ["", "If one of those is the board, name it directly:",
                  f"    python3 capture.py -p {usb[0][0]} -o byd-2013"]
        return "\n".join(lines)

    lines += ["", "Try these in order - the first is the usual cause:", "",
              "  1. Swap the USB cable. Charge-only cables carry power but no",
              "     data, so the board lights up and stays invisible.",
              "  2. Push the connector fully home; it seats loosely.",
              "  3. Windows: install the CH343 driver from wch-ic.com, then",
              "     look for a COM port in Device Manager.",
              "  4. Linux: run  lsusb  and look for 1a86:55d4. If it is there",
              "     but no port appears, it is a permissions problem:",
              "         sudo usermod -aG dialout $USER   (then log out and in)"]
    if builtin:
        lines += ["", f"({len(builtin)} built-in serial ports were found and "
                      "ignored - none of them is a USB board.)"]
    return "\n".join(lines)


def start_key_forwarder(ser):
    """Send keystrokes to the board without echoing them into the log.

    cbreak rather than raw: it turns off line buffering and echo but leaves
    signal handling alone, so Ctrl-C still stops the capture instead of being
    forwarded to the ESP32 as a character.
    """
    if not sys.stdin.isatty():
        return None
    try:
        import termios
        import tty
    except ImportError:
        return None            # Windows: capture still works, keys do not

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    def pump():
        while True:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            ch = os.read(fd, 1)
            if not ch:
                return
            try:
                ser.write(ch)
            except Exception:
                return

    threading.Thread(target=pump, daemon=True).start()
    return (fd, saved)


def stop_key_forwarder(restore):
    import termios
    fd, saved = restore
    termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def main():
    ap = argparse.ArgumentParser(description="Capture the Motivue serial log.")
    ap.add_argument("-p", "--port", help="serial port (auto-detected if omitted)")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-o", "--name", default="capture",
                    help="name for this capture, e.g. the car")
    ap.add_argument("-d", "--dir", default="captures", help="output directory")
    ap.add_argument("--no-reset", action="store_true",
                    help="do not reset the board on connect")
    ap.add_argument("--no-input", action="store_true",
                    help="do not forward typed keys to the board")
    ap.add_argument("--list", action="store_true",
                    help="list every serial port this machine reports, then exit")
    args = ap.parse_args()

    if args.list:
        found = list_ports()
        if not found:
            print("This machine reports no serial ports at all.")
        for dev, label, usb in found:
            print(f"{'USB ' if usb else '    '} {dev}    {label}")
        return

    port = args.port or find_port()
    if not port:
        sys.exit(no_port_message())

    os.makedirs(args.dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", args.name).strip("-") or "capture"
    full_path = os.path.join(args.dir, f"{slug}-{stamp}.txt")
    probe_path = os.path.join(args.dir, f"{slug}-{stamp}-probe.txt")

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = args.baud
    ser.timeout = 0.5
    # Both lines deasserted, or opening the port drives the auto-reset circuit
    # and we lose the boot banner we came for.
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.dtr = False
    ser.rts = False

    if not args.no_reset:
        # Pulse EN so the capture starts from a clean boot - the probe only
        # runs once, at startup.
        ser.rts = True
        import time
        time.sleep(0.12)
        ser.rts = False

    restore = None
    if not args.no_input:
        restore = start_key_forwarder(ser)

    print(f"port    {port} @ {args.baud}")
    print(f"log     {full_path}")
    print(f"probe   {probe_path}")
    if restore:
        print("keys    a/h left  d/l right  o/Enter select  b/q back")
    print("Ctrl-C to stop.\n")

    in_probe = False
    probe_lines = 0

    try:
        with open(full_path, "w", buffering=1) as full, \
             open(probe_path, "w", buffering=1) as probe:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                line = ANSI.sub("", raw.decode("utf-8", "replace")).rstrip("\r\n")

                full.write(line + "\n")
                sys.stdout.write(line + "\n")
                sys.stdout.flush()

                match = PROBE_LINE.search(line)
                if not match:
                    continue
                body = match.group(1)

                if PROBE_START in body:
                    in_probe = True
                if in_probe:
                    probe.write(body + "\n")
                    probe_lines += 1
                if PROBE_END in body:
                    in_probe = False
    except KeyboardInterrupt:
        pass
    finally:
        if restore:
            stop_key_forwarder(restore)
        ser.close()

    print(f"\nSaved {full_path}")
    if probe_lines:
        print(f"Saved {probe_path} ({probe_lines} lines)")
    else:
        print("No probe report seen. Reset the board while this is running.")
        print("Check that 'Run the OBD probe once at boot' is enabled.")


if __name__ == "__main__":
    main()
