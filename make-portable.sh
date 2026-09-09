#!/usr/bin/env bash
# Build a self-contained capture kit for a laptop that has nothing installed.
#
# The laptop that goes to the car is not the laptop the firmware was built on.
# It needs no ESP-IDF, no toolchain and no compiler - the board is already
# flashed, and capture.py only reads a serial port. All it needs is Python 3
# and pyserial, and pyserial is pure Python, so it travels by copy.
#
# That matters because a car park has no internet, and "pip install" is not a
# step you want to discover you cannot complete once you are already there.
#
# Usage:  tools/make-portable.sh [output-dir]

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$(dirname "$HERE")/motivue-capture}"

# pyserial ships inside the ESP-IDF virtualenv on the build machine. Take it
# from wherever this machine actually has it rather than assuming a path.
SRC=""
for PY in "$HOME"/.espressif/python_env/*/bin/python python3; do
    [ -x "$PY" ] || command -v "$PY" >/dev/null 2>&1 || continue
    if CAND=$("$PY" -c 'import serial,os;print(os.path.dirname(serial.__file__))' 2>/dev/null); then
        SRC="$CAND"
        break
    fi
done

if [ -z "$SRC" ]; then
    echo "Could not find pyserial on this machine to copy." >&2
    echo "Source the IDF environment first: . \$HOME/esp/esp-idf/export.sh" >&2
    exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"
cp "$HERE/capture.py" "$OUT/"
cp -r "$SRC" "$OUT/serial"
# Caches are built for this machine's interpreter and are dead weight elsewhere.
find "$OUT/serial" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$OUT/README.txt" <<'TXT'
Motivue capture kit
===================

Everything needed to capture an OBD session. No ESP-IDF, no toolchain, no
internet. The ESP32 is already flashed; this only reads its serial output and
sends key presses back.

REQUIREMENT
    Python 3.6 or newer. That is the whole list - pyserial is in this folder.

RUN IT
    cd into this folder, then:

        python3 capture.py -o byd-2013

    It resets the board so the capture starts from a clean boot, then writes:

        captures/lancer-2007-<timestamp>.txt         everything
        captures/lancer-2007-<timestamp>-probe.txt   just the OBD report

    Ctrl-C to stop. Every line is written to disk as it arrives, so a knocked
    cable never costs you more than the part that had not happened yet.

DRIVE THE INTERFACE WHILE IT RUNS
    Arrow keys       move / select
    Enter            open
    Backspace        back

IF IT SAYS "No serial port found"
    Linux   ls /dev/ttyACM*      should list ttyACM0
            Nothing there means the cable is charge-only or not fully seated.
            Try the other cable before anything else.

    Permission denied on Linux:
            sudo usermod -aG dialout $USER     then log out and back in
            or, just for now:  sudo chmod 666 /dev/ttyACM0

    Windows Install the CH343 / CH34x driver from wch-ic.com, then use the COM
            port:  python capture.py -p COM3

    macOS   Works out of the box.  ls /dev/cu.*    then pass -p

IN THE CAR
    Ignition ON, engine OFF for the first run.
    OBD pin 4 or 5 -> transceiver GND   (connect this one first)
    OBD pin 6      -> CANH
    OBD pin 14     -> CANL
    OBD pin 16     -> NOT CONNECTED. Power comes from this laptop.

WHAT TO LOOK FOR
    Near the top of the log, the CAN self test must pass. If it says the frame
    is stuck in the TX queue, the transceiver is not wired or not powered -
    stop and fix that, because a silent car and a broken controller look
    identical in the log.

    Then the variant sweep tries all four ISO 15765-4 combinations. What four
    "no answer" lines mean depends entirely on the car:

      2008 or newer   Almost certainly a WIRING FAULT, not the car. CAN was
                      effectively universal by then. Check, in this order:
                        1. CANH on pin 6 and CANL on pin 14, not swapped
                        2. ground actually connected to pin 4 or 5
                        3. the 120 ohm terminator on the transceiver board -
                           measure CANH to CANL with it disconnected from
                           everything. If it reads ~120 ohm, remove or lift
                           it: the car is already terminated, and a third
                           resistor takes the bus out of spec.

      pre-2008        A genuine result. The car speaks K-Line rather than CAN,
                      which is exactly what Phase 0 exists to find out.
TXT

BYTES=$(du -sh "$OUT" | cut -f1)
echo "Built $OUT ($BYTES)"
echo
echo "Copy that whole folder to the other laptop, then run:"
echo "    cd motivue-capture && python3 capture.py -o byd-2013"
