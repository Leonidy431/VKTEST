#ifndef ZERO_CROSSING_H
#define ZERO_CROSSING_H

#include <stdint.h>

/*
 * Детектор перехода через ноль (99 факт #19) и планировщик импульса
 * симистора. Компаратор (LM393) на первичной обмотке генерирует фронт на
 * GPIO при пересечении нуля сетевым напряжением; прерывание запускает
 * high-resolution таймер на задержку delay_us перед импульсом на затвор.
 */

#define ZC_GPIO_PIN            4   /* GPIO для входа детектора перехода через ноль */
#define TRIAC_GATE_GPIO_PIN    5   /* GPIO -> оптрон MOC3083 -> затвор симистора */
#define TRIAC_PULSE_WIDTH_US   100 /* Длительность импульса на затвор */

void zero_crossing_init(void);

/* Планирует включение симистора через delay_us после следующего zero-cross. */
void zero_crossing_schedule_triac_pulse(uint32_t delay_us);

#endif /* ZERO_CROSSING_H */
