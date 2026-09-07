/*
 * Motivue smoke test.
 *
 * Not part of the product. This exists to answer one question before any real
 * work happens on the board: does the whole chain work -- USB cable, serial
 * bridge, toolchain, flashing, boot, and reset?
 *
 * It blinks the onboard LED and prints a heartbeat, so it gives an answer even
 * on a DevKit clone that has no user LED fitted.
 */

#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"

/* Most 38-pin DOIT/DevKitC-style ESP32 boards put the blue user LED on GPIO 2.
 * Some clones fit only a power LED. If nothing blinks but the heartbeat prints,
 * the board is fine -- try 16, or just trust the serial output. */
#define LED_GPIO 2

#define BLINK_PERIOD_MS 1000

static const char *TAG = "blink";

static void report_chip(void)
{
    esp_chip_info_t info;
    esp_chip_info(&info);

    uint32_t flash_size = 0;
    if (esp_flash_get_size(NULL, &flash_size) != ESP_OK) {
        flash_size = 0;
    }

    /* esp_chip_info_t.revision is encoded as major*100 + minor. */
    ESP_LOGI(TAG, "chip: %s, %d core(s), silicon revision v%d.%d",
             CONFIG_IDF_TARGET, info.cores, info.revision / 100, info.revision % 100);
    ESP_LOGI(TAG, "radio: %s%s%s",
             (info.features & CHIP_FEATURE_WIFI_BGN) ? "WiFi " : "",
             (info.features & CHIP_FEATURE_BT) ? "BT-Classic " : "",
             (info.features & CHIP_FEATURE_BLE) ? "BLE" : "");
    ESP_LOGI(TAG, "flash: %" PRIu32 " MB %s", flash_size / (1024 * 1024),
             (info.features & CHIP_FEATURE_EMB_FLASH) ? "embedded" : "external");
    ESP_LOGI(TAG, "free heap: %" PRIu32 " bytes", esp_get_free_heap_size());
}

void app_main(void)
{
    ESP_LOGI(TAG, "Motivue board smoke test");
    report_chip();
    ESP_LOGI(TAG, "blinking GPIO %d every %d ms", LED_GPIO, BLINK_PERIOD_MS);

    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);

    bool on = false;
    uint32_t count = 0;

    for (;;) {
        on = !on;
        gpio_set_level(LED_GPIO, on);
        if (on) {
            ESP_LOGI(TAG, "blink %" PRIu32 " -- board alive", ++count);
        }
        vTaskDelay(pdMS_TO_TICKS(BLINK_PERIOD_MS / 2));
    }
}
