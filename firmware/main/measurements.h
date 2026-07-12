#ifndef MEASUREMENTS_H
#define MEASUREMENTS_H

#include <stdint.h>

/*
 * Сенсорика: АЦП (напряжение, ток через датчик Холла ACS758), температура
 * (DS18B20). Опрос не реже 1кГц для True RMS (99 факт #29-30).
 */

#define ADC_CHANNEL_VOLTAGE   0  /* Делитель напряжения вторичной обмотки */
#define ADC_CHANNEL_CURRENT   1  /* ACS758LCB, гальванически развязан */
#define ADC_SAMPLE_RATE_HZ    1000

void measurements_init(void);

/* Возвращают мгновенные значения после калибровки делителя/датчика Холла. */
float measurements_read_voltage(void);
float measurements_read_current(void);

/* True RMS за последний период (накапливается внутренним буфером). */
float measurements_get_voltage_rms(void);
float measurements_get_current_rms(void);

float measurements_read_heatsink_temp_c(void);   /* DS18B20 на радиаторе */
float measurements_read_ambient_temp_c(void);    /* DS18B20 снаружи корпуса */

#endif /* MEASUREMENTS_H */
