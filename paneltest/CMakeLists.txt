cmake_minimum_required(VERSION 3.16)

# Reuse the product's display driver rather than a copy, so this test exercises
# exactly the code path the real firmware uses - same panel drivers, same
# orientation settings, same Kconfig. A fault report and the real build can
# then never disagree about how the panel was driven.
#
# Only the panel layer, though. This tool deliberately runs without LVGL: its
# whole purpose is to prove a panel fault with nothing between the controller
# and the glass, so nobody can blame the UI for what it shows.
set(EXTRA_COMPONENT_DIRS
    "../../firmware/components/mv_display"
    "../../firmware/components/mv_board")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(mv_paneltest)
