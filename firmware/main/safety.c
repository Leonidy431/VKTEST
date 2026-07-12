#include "safety.h"
#include <math.h>

void safety_limits_default(safety_limits_t *limits)
{
    limits->min_input_voltage = 185.0f;
    limits->short_circuit_current_a = 120.0f;
    limits->min_freq_hz = 45.0f;
    limits->max_freq_hz = 65.0f;
    limits->max_heatsink_temp_c = 70.0f;
    limits->critical_heatsink_temp_c = 80.0f;
    limits->min_battery_voltage = 42.0f;
    limits->min_operating_temp_c = -20.0f;
}

safety_violation_t safety_check_pre_start(
    const safety_limits_t *limits,
    float input_voltage,
    float mains_freq_hz,
    float ambient_temp_c,
    float battery_voltage,
    int battery_present)
{
    if (input_voltage < limits->min_input_voltage) {
        return SAFETY_LOW_INPUT_VOLTAGE;
    }
    if (mains_freq_hz < limits->min_freq_hz || mains_freq_hz > limits->max_freq_hz) {
        return SAFETY_FREQUENCY_OUT_OF_RANGE;
    }
    if (ambient_temp_c < limits->min_operating_temp_c) {
        return SAFETY_AMBIENT_TOO_COLD;
    }
    if (battery_present && battery_voltage < limits->min_battery_voltage) {
        return SAFETY_BATTERY_LOW;
    }
    return SAFETY_OK;
}

safety_violation_t safety_check_during_weld(
    const safety_limits_t *limits,
    float current_a,
    float heatsink_temp_c)
{
    if (current_a <= 0.01f) {
        return SAFETY_OPEN_CIRCUIT;
    }
    if (current_a > limits->short_circuit_current_a) {
        return SAFETY_SHORT_CIRCUIT;
    }
    if (heatsink_temp_c > limits->critical_heatsink_temp_c) {
        return SAFETY_OVERHEAT_CRITICAL;
    }
    return SAFETY_OK;
}

int safety_should_derate(const safety_limits_t *limits, float heatsink_temp_c)
{
    return heatsink_temp_c > limits->max_heatsink_temp_c &&
           heatsink_temp_c <= limits->critical_heatsink_temp_c;
}
