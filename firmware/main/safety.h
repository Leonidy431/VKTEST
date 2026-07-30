#ifndef SAFETY_H
#define SAFETY_H

/*
 * Защиты и лимиты безопасности — портированы из control/safety_validator.py.
 * Значения синхронизированы с 99 фактами (#86-90) и провалидированы тестами
 * tests/test_safety_validators.py.
 */

typedef struct {
    float min_input_voltage;       /* 185.0 V */
    float max_current_a;           /* 110.0 A - рабочий максимум (мягкий предел) */
    float short_circuit_current_a; /* 120.0 A - аппаратный предел КЗ */
    float min_freq_hz;             /* 45.0 Hz */
    float max_freq_hz;             /* 65.0 Hz */
    float max_heatsink_temp_c;     /* 70.0 C  - начало derating */
    float critical_heatsink_temp_c;/* 80.0 C  - аварийное отключение */
    float min_battery_voltage;     /* 42.0 V  - отсечка BMS */
    float min_operating_temp_c;    /* -20.0 C */
} safety_limits_t;

typedef enum {
    SAFETY_OK = 0,
    SAFETY_LOW_INPUT_VOLTAGE,
    SAFETY_FREQUENCY_OUT_OF_RANGE,
    SAFETY_AMBIENT_TOO_COLD,
    SAFETY_BATTERY_LOW,
    SAFETY_OPEN_CIRCUIT,
    SAFETY_SHORT_CIRCUIT,
    SAFETY_OVERCURRENT,
    SAFETY_OVERHEAT_CRITICAL,
} safety_violation_t;

void safety_limits_default(safety_limits_t *limits);

safety_violation_t safety_check_pre_start(
    const safety_limits_t *limits,
    float input_voltage,
    float mains_freq_hz,
    float ambient_temp_c,
    float battery_voltage,
    int battery_present
);

safety_violation_t safety_check_during_weld(
    const safety_limits_t *limits,
    float current_a,
    float heatsink_temp_c
);

/* 99 факт #17: derating мощности на 30% при 70°C < T <= 80°C */
int safety_should_derate(const safety_limits_t *limits, float heatsink_temp_c);

#endif /* SAFETY_H */
