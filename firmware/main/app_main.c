#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "pid_controller.h"
#include "state_machine.h"
#include "safety.h"
#include "measurements.h"
#include "zero_crossing.h"

#define WELD_TARGET_VOLTAGE   39.5f
#define MAINS_FREQ_HZ         50.0f
#define CONTROL_LOOP_DT_S     0.02f  /* один полный цикл сети = 20мс при 50Гц */
#define SAMPLING_PERIOD_MS    1      /* 1кГц опрос АЦП для True RMS, см. measurements.h */

static pid_controller_t s_pid;
static welding_state_machine_t s_sm;
static safety_limits_t s_limits;

/*
 * Задача опроса АЦП — заполняет скользящие окна True RMS в measurements.c.
 * Без нее measurements_get_voltage_rms()/measurements_get_current_rms()
 * читают вечно обнуленные буферы: ток всегда 0А, и первая же итерация
 * weld_control_task ошибочно фиксирует SAFETY_OPEN_CIRCUIT еще до входа
 * в pid_update() (найдено при аудите — ранее эта задача отсутствовала).
 */
static void measurement_sampling_task(void *pvParameters)
{
    for (;;) {
        measurements_read_voltage();
        measurements_read_current();
        vTaskDelay(pdMS_TO_TICKS(SAMPLING_PERIOD_MS));
    }
}

/*
 * Задача управления сваркой — центральный цикл ~50 раз/сек, синхронизированный
 * с частотой сети через zero_crossing (в реальной прошивке цикл запускался бы
 * из обработчика zero-cross, здесь — периодическая FreeRTOS задача как каркас).
 */
static void weld_control_task(void *pvParameters)
{
    for (;;) {
        if (s_sm.state == WELD_STATE_HEATING) {
            float voltage = measurements_get_voltage_rms();
            float current = measurements_get_current_rms();
            float heatsink_temp = measurements_read_heatsink_temp_c();

            safety_violation_t fault = safety_check_during_weld(&s_limits, current, heatsink_temp);
            if (fault != SAFETY_OK) {
                wsm_raise_error(&s_sm, "safety fault during weld");
            } else {
                float angle = pid_update(&s_pid, voltage, CONTROL_LOOP_DT_S);
                uint32_t delay_us = (uint32_t)pid_angle_to_delay_us(angle, MAINS_FREQ_HZ);
                zero_crossing_schedule_triac_pulse(delay_us);
            }
        }

        vTaskDelay(pdMS_TO_TICKS((int)(CONTROL_LOOP_DT_S * 1000)));
    }
}

void app_main(void)
{
    pid_init(&s_pid, WELD_TARGET_VOLTAGE);
    wsm_init(&s_sm);
    safety_limits_default(&s_limits);

    measurements_init();
    zero_crossing_init();

    xTaskCreate(measurement_sampling_task, "meas_sampling", 2048, NULL, 12, NULL);
    xTaskCreate(weld_control_task, "weld_control", 4096, NULL, 10, NULL);

    /*
     * Остальная периферия (сканер штрих-кода, дисплей, SD-логирование,
     * Wi-Fi/BLE синхронизация) инициализируется отдельными задачами —
     * см. docs/architecture.md для полной схемы разбиения на FreeRTOS задачи.
     */
}
