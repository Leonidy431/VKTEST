"""
ПИД-регулятор для стабилизации выходного напряжения сварки.

Задача: удерживать U_out = target (обычно 39.5V) вне зависимости от
просадок входного питания (батарея разряжается, сеть проседает под нагрузкой)
или изменения сопротивления спирали при нагреве.

Выход регулятора — угол открытия симистора в градусах (0..180), который
затем конвертируется в задержку от точки перехода через ноль (zero-cross).
"""

from dataclasses import dataclass, field


@dataclass
class PIDVoltageRegulator:
    target_voltage: float = 39.5
    kp: float = 1.5
    ki: float = 2.5
    kd: float = 0.02
    min_angle_deg: float = 0.0
    max_angle_deg: float = 180.0

    _integral: float = field(default=0.0, init=False)
    _last_error: float = field(default=0.0, init=False)
    _initialized: bool = field(default=False, init=False)

    def reset(self) -> None:
        self._integral = 0.0
        self._last_error = 0.0
        self._initialized = False

    def update(self, measured_voltage: float, dt: float) -> float:
        """
        Один шаг ПИД-регулятора. Возвращает угол открытия симистора (градусы).
        Меньший угол => раньше включение => больше энергии передано за полупериод.

        control_signal ограничен диапазоном [-90, 90], так как angle = 90 - control_signal
        должен укладываться в физический диапазон угла симистора [0, 180]. Интегральная
        составляющая накапливается только если выход не насыщен в сторону текущей ошибки
        (conditional anti-windup) — иначе интеграл "залипает" далеко за пределами
        значения, реально нужного для достижения угла 0 или 180.
        """
        error = self.target_voltage - measured_voltage
        signal_limit = 90.0

        derivative = 0.0
        if self._initialized and dt > 0:
            derivative = (error - self._last_error) / dt

        unsaturated_signal = self.kp * error + self.ki * self._integral + self.kd * derivative
        is_saturated_high = unsaturated_signal >= signal_limit and error > 0
        is_saturated_low = unsaturated_signal <= -signal_limit and error < 0
        if not (is_saturated_high or is_saturated_low):
            self._integral += error * dt

        control_signal = self.kp * error + self.ki * self._integral + self.kd * derivative
        control_signal = max(-signal_limit, min(signal_limit, control_signal))

        # Больше error (просадка) => нужно больше мощности => угол ближе к 0.
        angle = 90.0 - control_signal
        angle = max(self.min_angle_deg, min(self.max_angle_deg, angle))

        self._last_error = error
        self._initialized = True
        return angle

    @staticmethod
    def angle_to_delay_us(angle_deg: float, mains_freq_hz: float = 50.0) -> float:
        """
        Конвертирует угол открытия симистора (0..180°) в задержку в
        микросекундах от точки перехода через ноль до момента включения.
        """
        half_period_us = (1.0 / mains_freq_hz) * 1_000_000 / 2.0
        return (angle_deg / 180.0) * half_period_us

    @staticmethod
    def angle_to_rms_voltage(angle_deg: float, peak_voltage: float) -> float:
        """
        Приблизительное действующее (RMS) напряжение при фазовом управлении
        симистором с углом открытия angle_deg (0 = полностью открыт, 180 = закрыт).

        V_rms = V_peak * sqrt( (1/(2*pi)) * (pi - alpha + sin(2*alpha)/2) ), alpha в радианах.
        При alpha=0 (полностью открыт) V_rms = V_peak/sqrt(2) — полная синусоида.
        """
        import math

        alpha = math.radians(angle_deg)
        term = (math.pi - alpha + math.sin(2 * alpha) / 2) / (2 * math.pi)
        term = max(0.0, term)
        return peak_voltage * math.sqrt(term)
