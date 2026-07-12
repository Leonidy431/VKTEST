"""
Моделирование источников питания портативного аппарата:
  - 48V LiFePO4 батарея (просадка напряжения при разрядке и под нагрузкой)
  - Сеть 220В (просадки от генератора, шум, отклонения частоты)

Используется для стресс-тестирования ПИД-регулятора и физического движка
в условиях, приближенных к полевым (просадки, нестабильная частота).
"""

import math
from dataclasses import dataclass


@dataclass
class LiFePO4Battery:
    """
    Упрощенная модель батареи 48V LiFePO4 30Ah (~1440Wh).

    Напряжение холостого хода зависит от уровня заряда (SoC), напряжение под
    нагрузкой дополнительно проседает пропорционально внутреннему сопротивлению.
    """

    capacity_ah: float = 30.0
    nominal_voltage: float = 51.2  # 16S LiFePO4 (16 * 3.2V)
    internal_resistance_ohm: float = 0.015
    soc: float = 1.0  # 0..1, начальный заряд
    min_soc: float = 0.10  # BMS отключает ниже этого порога

    _consumed_ah: float = 0.0

    def open_circuit_voltage(self) -> float:
        """
        Приближенная кривая разряда LiFePO4: плато ~51-53V до глубокой
        разрядки, затем резкий спад после SoC < 15%.
        """
        if self.soc > 0.15:
            # Плато: 52.8V (100%) -> 51.2V (15%)
            return 51.2 + (self.soc - 0.15) / 0.85 * 1.6
        else:
            # Резкий спад к 40V при полном истощении
            return 40.0 + (self.soc / 0.15) * 11.2

    def voltage_under_load(self, current_a: float) -> float:
        ocv = self.open_circuit_voltage()
        return max(0.0, ocv - current_a * self.internal_resistance_ohm)

    def draw_current(self, current_a: float, dt_s: float) -> float:
        """Списывает заряд за интервал dt_s, возвращает фактическое напряжение под нагрузкой."""
        ah_drawn = current_a * (dt_s / 3600.0)
        self._consumed_ah += ah_drawn
        self.soc = max(0.0, 1.0 - self._consumed_ah / self.capacity_ah)
        if self.soc <= self.min_soc:
            raise BatteryDepletedError(
                f"SoC {self.soc:.1%} at or below BMS cutoff {self.min_soc:.0%}"
            )
        return self.voltage_under_load(current_a)

    def welds_remaining(self, energy_per_weld_wh: float = 45.0) -> int:
        usable_wh = (self.soc - self.min_soc) * self.capacity_ah * self.nominal_voltage
        return max(0, int(usable_wh // energy_per_weld_wh))


class BatteryDepletedError(RuntimeError):
    pass


@dataclass
class MainsSupply:
    """
    Модель сети 220В (или дизель-генератора) с возможностью просадок,
    шума и отклонений частоты — для тестов защит аппарата.
    """

    nominal_voltage: float = 220.0
    nominal_freq_hz: float = 50.0
    sag_voltage: float = 0.0  # постоянная просадка, В
    noise_amplitude: float = 0.0  # амплитуда шума, В
    freq_drift_hz: float = 0.0

    def instantaneous_voltage(self, t: float) -> float:
        base = self.nominal_voltage - self.sag_voltage
        noise = self.noise_amplitude * math.sin(37.0 * t)  # высокочастотная помеха
        return base + noise

    def frequency(self) -> float:
        return self.nominal_freq_hz + self.freq_drift_hz

    def is_within_safe_bounds(self) -> bool:
        """99 факт #89-90: блокировка при U < 185В или f вне 45-65 Гц."""
        v = self.nominal_voltage - self.sag_voltage
        f = self.frequency()
        return v >= 185.0 and 45.0 <= f <= 65.0
