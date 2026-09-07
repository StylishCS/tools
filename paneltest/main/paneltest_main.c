/*
 * Panel fault test.
 *
 * Fills the whole screen with one flat colour at a time. Every pixel gets the
 * same value, so nothing drawn can vary across the glass.
 *
 * That is the whole point: if a mark, line, blotch or band stays in the same
 * physical place through red, green, blue, white AND black, no software can be
 * producing it -- the fault is in the panel or its ribbon. If instead the marks
 * move, change, or disappear between colours, the problem is signal integrity
 * (wiring, SPI clock, supply) and the panel may be fine.
 */

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "mv_display.h"

static const char *TAG = "paneltest";

#define HOLD_MS 3000


void app_main(void)
{
    ESP_LOGI(TAG, "panel fault test - solid colour sweep");

    if (mv_display_init() != ESP_OK || !mv_display_present()) {
        ESP_LOGE(TAG, "no panel detected - check wiring");
        return;
    }
    mv_display_backlight(true);

    ESP_LOGI(TAG, "%s %dx%d", mv_display_panel_name(),
             mv_display_width(), mv_display_height());

    const struct { const char *name; uint16_t color; } STEPS[] = {
        {"RED",   MV_RGB(255, 0, 0)},
        {"GREEN", MV_RGB(0, 255, 0)},
        {"BLUE",  MV_RGB(0, 0, 255)},
        {"WHITE", MV_RGB(255, 255, 255)},
        {"BLACK", MV_RGB(0, 0, 0)},
    };
    const int n = sizeof(STEPS) / sizeof(STEPS[0]);

    for (int i = 0; ; i = (i + 1) % n) {
        ESP_LOGI(TAG, "fill %s", STEPS[i].name);
        mv_display_clear(STEPS[i].color);
        vTaskDelay(pdMS_TO_TICKS(HOLD_MS));
    }
}
