#include "zero_crossing.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_attr.h"

static esp_timer_handle_t s_triac_on_timer = NULL;
static esp_timer_handle_t s_triac_off_timer = NULL;

static void IRAM_ATTR triac_on_callback(void *arg)
{
    gpio_set_level(TRIAC_GATE_GPIO_PIN, 1);
    esp_timer_start_once(s_triac_off_timer, TRIAC_PULSE_WIDTH_US);
}

static void IRAM_ATTR triac_off_callback(void *arg)
{
    gpio_set_level(TRIAC_GATE_GPIO_PIN, 0);
}

static void IRAM_ATTR zero_cross_isr_handler(void *arg)
{
    /*
     * Обработчик прерывания только уведомляет: реальное планирование
     * импульса выполняется через zero_crossing_schedule_triac_pulse(),
     * вызываемый из основного цикла управления после расчета угла ПИД.
     * Здесь оставлено место для событийного флага/очереди FreeRTOS,
     * если требуется полностью автономная (без опроса) синхронизация.
     */
}

void zero_crossing_init(void)
{
    gpio_config_t zc_conf = {
        .pin_bit_mask = 1ULL << ZC_GPIO_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    gpio_config(&zc_conf);

    gpio_config_t triac_conf = {
        .pin_bit_mask = 1ULL << TRIAC_GATE_GPIO_PIN,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&triac_conf);
    gpio_set_level(TRIAC_GATE_GPIO_PIN, 0);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(ZC_GPIO_PIN, zero_cross_isr_handler, NULL);

    const esp_timer_create_args_t on_args = {
        .callback = &triac_on_callback,
        .name = "triac_on",
    };
    esp_timer_create(&on_args, &s_triac_on_timer);

    const esp_timer_create_args_t off_args = {
        .callback = &triac_off_callback,
        .name = "triac_off",
    };
    esp_timer_create(&off_args, &s_triac_off_timer);
}

void zero_crossing_schedule_triac_pulse(uint32_t delay_us)
{
    esp_timer_start_once(s_triac_on_timer, delay_us);
}
