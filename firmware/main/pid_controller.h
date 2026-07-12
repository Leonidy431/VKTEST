#ifndef PID_CONTROLLER_H
#define PID_CONTROLLER_H

/*
 * ПИД-регулятор напряжения сварки — портирован из simulation/pid_simulator.py.
 * Коэффициенты подобраны и провалидированы в Python-симуляции
 * (tests/test_pid_controller.py): kp=1.5, ki=2.5, kd=0.02.
 *
 * Использует conditional anti-windup: интеграл не накапливается, если выход
 * уже насыщен в направлении текущей ошибки (см. обоснование в .py версии —
 * без этого интеграл "залипает" далеко за пределы, нужные для угла 0/180).
 */

typedef struct {
    float target_voltage;
    float kp;
    float ki;
    float kd;
    float min_angle_deg;
    float max_angle_deg;

    float integral;
    float last_error;
    int initialized;
} pid_controller_t;

void pid_init(pid_controller_t *pid, float target_voltage);
void pid_reset(pid_controller_t *pid);

/* Один шаг регулятора. Возвращает угол открытия симистора в градусах [0,180]. */
float pid_update(pid_controller_t *pid, float measured_voltage, float dt_s);

/* Конвертация угла в задержку от zero-cross (микросекунды). */
float pid_angle_to_delay_us(float angle_deg, float mains_freq_hz);

#endif /* PID_CONTROLLER_H */
