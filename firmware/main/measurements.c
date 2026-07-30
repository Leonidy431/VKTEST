#include "measurements.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include <math.h>
#include <string.h>

/*
 * Калибровочные коэффициенты делителя напряжения и датчика Холла.
 * Значения — placeholder-и, требующие уточнения на реальном стенде через
 * заводскую калибровку (99 факт #95).
 */
#define VOLTAGE_DIVIDER_RATIO   17.0f  /* 56V -> ~3.3V на АЦП */
/*
 * ACS758LCB-150B: 13.3мВ/А. Ранее здесь стояло 40.0f (чувствительность
 * 050B-варианта, рассчитанного на 50А) при том, что short_circuit_current_a
 * в safety.h равен 120А — 050B физически не мог измерить ток КЗ (насыщался
 * бы задолго до порога). BOM обновлен на 150B (hardware/bom.csv), константа
 * согласована с новым датчиком.
 */
#define ACS758_MV_PER_AMP       13.3f  /* ACS758LCB-150B: 13.3мВ/А */
#define ACS758_ZERO_CURRENT_MV  1650.0f /* Vcc/2 при токе 0А */

#define RMS_WINDOW_SIZE 20  /* окно для скользящего True RMS (при 1кГц ~20мс = 1 период 50Гц) */

static adc_oneshot_unit_handle_t s_adc_handle = NULL;
static adc_cali_handle_t s_cali_handle = NULL;

static float s_voltage_window[RMS_WINDOW_SIZE];
static float s_current_window[RMS_WINDOW_SIZE];
/*
 * Раздельные индексы для каждого канала: измерение напряжения и тока не
 * обязаны вызываться строго попарно 1:1 за каждый цикл (например, UI может
 * опрашивать напряжение отдельно). Общий индекс, инкрементируемый только в
 * measurements_read_current(), приводил бы к десинхронизации окон при любом
 * несимметричном вызове каналов.
 */
static int s_voltage_idx = 0;
static int s_current_idx = 0;

void measurements_init(void)
{
    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
    };
    adc_oneshot_new_unit(&init_cfg, &s_adc_handle);

    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    adc_oneshot_config_channel(s_adc_handle, ADC_CHANNEL_VOLTAGE, &chan_cfg);
    adc_oneshot_config_channel(s_adc_handle, ADC_CHANNEL_CURRENT, &chan_cfg);

    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_cali_handle);

    memset(s_voltage_window, 0, sizeof(s_voltage_window));
    memset(s_current_window, 0, sizeof(s_current_window));
}

float measurements_read_voltage(void)
{
    int raw = 0;
    int mv = 0;
    adc_oneshot_read(s_adc_handle, ADC_CHANNEL_VOLTAGE, &raw);
    adc_cali_raw_to_voltage(s_cali_handle, raw, &mv);
    float voltage = (mv / 1000.0f) * VOLTAGE_DIVIDER_RATIO;

    s_voltage_window[s_voltage_idx % RMS_WINDOW_SIZE] = voltage;
    s_voltage_idx++;
    return voltage;
}

float measurements_read_current(void)
{
    int raw = 0;
    int mv = 0;
    adc_oneshot_read(s_adc_handle, ADC_CHANNEL_CURRENT, &raw);
    adc_cali_raw_to_voltage(s_cali_handle, raw, &mv);
    float current = (mv - ACS758_ZERO_CURRENT_MV) / ACS758_MV_PER_AMP;

    s_current_window[s_current_idx % RMS_WINDOW_SIZE] = current;
    s_current_idx++;
    return current;
}

static float compute_rms(const float *window, int size)
{
    float sum_sq = 0.0f;
    for (int i = 0; i < size; i++) {
        sum_sq += window[i] * window[i];
    }
    return sqrtf(sum_sq / size);
}

float measurements_get_voltage_rms(void)
{
    return compute_rms(s_voltage_window, RMS_WINDOW_SIZE);
}

float measurements_get_current_rms(void)
{
    return compute_rms(s_current_window, RMS_WINDOW_SIZE);
}

/*
 * DS18B20 (1-Wire) требует полноценного протокола presence/reset/ROM/scratchpad,
 * который в проекте предполагается использовать через готовый компонент
 * (например espressif/ds18b20 или owb+ds18b20 через ESP Component Registry),
 * а не переизобретать побитовый 1-Wire драйвер в этом файле. Здесь оставлены
 * тонкие обертки вокруг такого компонента для единообразия интерфейса.
 */
float measurements_read_heatsink_temp_c(void)
{
    /* TODO: интеграция с компонентом ds18b20 (см. docs/architecture.md) */
    return 25.0f;
}

float measurements_read_ambient_temp_c(void)
{
    /* TODO: интеграция с компонентом ds18b20 (см. docs/architecture.md) */
    return 20.0f;
}
