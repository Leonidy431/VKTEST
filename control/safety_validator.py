"""
Валидация безопасности перед и во время сварки (99 факт #86-90).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyLimits:
    min_input_voltage: float = 185.0
    max_current_a: float = 110.0
    short_circuit_current_a: float = 120.0
    min_freq_hz: float = 45.0
    max_freq_hz: float = 65.0
    max_heatsink_temp_c: float = 70.0
    critical_heatsink_temp_c: float = 80.0
    min_battery_voltage: float = 42.0  # BMS cutoff для 48V LiFePO4
    min_operating_temp_c: float = -20.0


@dataclass
class SafetyViolation:
    code: str
    message: str


class SafetyValidator:
    def __init__(self, limits: Optional[SafetyLimits] = None) -> None:
        self.limits = limits or SafetyLimits()

    def check_pre_start(
        self,
        input_voltage: float,
        mains_freq_hz: float,
        ambient_temp_c: float,
        battery_voltage: Optional[float] = None,
    ) -> Optional[SafetyViolation]:
        if input_voltage < self.limits.min_input_voltage:
            return SafetyViolation(
                "LOW_INPUT_VOLTAGE",
                f"Входное напряжение {input_voltage:.0f}В < {self.limits.min_input_voltage:.0f}В",
            )
        if not (self.limits.min_freq_hz <= mains_freq_hz <= self.limits.max_freq_hz):
            return SafetyViolation(
                "FREQUENCY_OUT_OF_RANGE",
                f"Частота сети {mains_freq_hz:.1f}Гц вне [{self.limits.min_freq_hz}, {self.limits.max_freq_hz}]Гц",
            )
        if ambient_temp_c < self.limits.min_operating_temp_c:
            return SafetyViolation(
                "AMBIENT_TOO_COLD",
                f"Температура {ambient_temp_c:.0f}°C ниже минимальной {self.limits.min_operating_temp_c:.0f}°C",
            )
        if battery_voltage is not None and battery_voltage < self.limits.min_battery_voltage:
            return SafetyViolation(
                "BATTERY_LOW",
                f"Напряжение батареи {battery_voltage:.1f}В ниже отсечки BMS {self.limits.min_battery_voltage:.1f}В",
            )
        return None

    def check_during_weld(self, current_a: float, heatsink_temp_c: float) -> Optional[SafetyViolation]:
        if current_a <= 0.01:
            return SafetyViolation("OPEN_CIRCUIT", "Ток упал до нуля — обрыв цепи")
        if current_a > self.limits.short_circuit_current_a:
            return SafetyViolation(
                "SHORT_CIRCUIT", f"Ток {current_a:.1f}А превышает лимит КЗ {self.limits.short_circuit_current_a}А"
            )
        if current_a > self.limits.max_current_a:
            return SafetyViolation(
                "OVERCURRENT",
                f"Ток {current_a:.1f}А превышает рабочий максимум {self.limits.max_current_a}А",
            )
        if heatsink_temp_c > self.limits.critical_heatsink_temp_c:
            return SafetyViolation(
                "OVERHEAT_CRITICAL",
                f"Температура радиатора {heatsink_temp_c:.0f}°C превышает критический предел",
            )
        return None

    def should_derate(self, heatsink_temp_c: float) -> bool:
        """99 факт #17: если T радиатора превышает порог — снижаем мощность на 30%."""
        return self.limits.max_heatsink_temp_c < heatsink_temp_c <= self.limits.critical_heatsink_temp_c
