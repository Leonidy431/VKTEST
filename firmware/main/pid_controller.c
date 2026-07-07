#include "pid_controller.h"

void pid_init(pid_controller_t *pid, float target_voltage)
{
    pid->target_voltage = target_voltage;
    pid->kp = 1.5f;
    pid->ki = 2.5f;
    pid->kd = 0.02f;
    pid->min_angle_deg = 0.0f;
    pid->max_angle_deg = 180.0f;
    pid_reset(pid);
}

void pid_reset(pid_controller_t *pid)
{
    pid->integral = 0.0f;
    pid->last_error = 0.0f;
    pid->initialized = 0;
}

float pid_update(pid_controller_t *pid, float measured_voltage, float dt_s)
{
    const float signal_limit = 90.0f;
    float error = pid->target_voltage - measured_voltage;

    float derivative = 0.0f;
    if (pid->initialized && dt_s > 0.0f) {
        derivative = (error - pid->last_error) / dt_s;
    }

    float unsaturated_signal = pid->kp * error + pid->ki * pid->integral + pid->kd * derivative;
    int is_saturated_high = (unsaturated_signal >= signal_limit) && (error > 0.0f);
    int is_saturated_low = (unsaturated_signal <= -signal_limit) && (error < 0.0f);
    if (!is_saturated_high && !is_saturated_low) {
        pid->integral += error * dt_s;
    }

    float control_signal = pid->kp * error + pid->ki * pid->integral + pid->kd * derivative;
    if (control_signal > signal_limit) control_signal = signal_limit;
    if (control_signal < -signal_limit) control_signal = -signal_limit;

    float angle = 90.0f - control_signal;
    if (angle < pid->min_angle_deg) angle = pid->min_angle_deg;
    if (angle > pid->max_angle_deg) angle = pid->max_angle_deg;

    pid->last_error = error;
    pid->initialized = 1;
    return angle;
}

float pid_angle_to_delay_us(float angle_deg, float mains_freq_hz)
{
    float half_period_us = (1.0f / mains_freq_hz) * 1000000.0f / 2.0f;
    return (angle_deg / 180.0f) * half_period_us;
}
