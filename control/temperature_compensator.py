"""
Температурная компенсация времени сварки (99 факт #6-9, #93).

При низкой температуре окружающей среды муфта теряет тепло в воздух быстрее,
поэтому базовое время нагрева из штрих-кода должно быть увеличено.
"""

from dataclasses import dataclass


@dataclass
class TemperatureCompensator:
    reference_temp_c: float = 20.0
    # Эмпирический коэффициент: +0.4% времени на каждый градус ниже reference
    compensation_per_degree: float = 0.004
    # Экспоненциальный рост компенсации при отрицательных температурах (99 факт #8)
    subzero_exponent_base: float = 1.015

    def compensate_heating_time(self, base_time_s: float, ambient_temp_c: float) -> float:
        if ambient_temp_c >= self.reference_temp_c:
            return base_time_s

        deficit = self.reference_temp_c - ambient_temp_c

        if ambient_temp_c >= 0:
            factor = 1.0 + deficit * self.compensation_per_degree
        else:
            # Линейная компенсация до 0°C, затем экспоненциальная ниже нуля
            linear_part = 1.0 + self.reference_temp_c * self.compensation_per_degree
            subzero_deficit = -ambient_temp_c
            factor = linear_part * (self.subzero_exponent_base ** subzero_deficit)

        return base_time_s * factor

    def compensate_cooling_time(self, base_cooling_s: float, ambient_temp_c: float) -> float:
        """При очень низкой температуре остывание идет быстрее — можно слегка сократить."""
        if ambient_temp_c >= self.reference_temp_c:
            return base_cooling_s
        deficit = self.reference_temp_c - ambient_temp_c
        # Не сокращаем более чем на 15% — безопасный консервативный предел
        reduction = min(0.15, deficit * 0.003)
        return base_cooling_s * (1.0 - reduction)
