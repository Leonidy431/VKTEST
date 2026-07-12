"""
Физический двигатель электромуфтовой сварки.

Реализует закон Джоуля-Ленца Q = (U^2 / R) * t с учетом нелинейного
изменения сопротивления нагревательной спирали при нагреве и температурной
компенсации для условий окружающей среды.
"""

from dataclasses import dataclass
from enum import Enum


class WeldState(Enum):
    INCOMPLETE_WELD = "INCOMPLETE_WELD"
    SUCCESS = "SUCCESS"
    THERMAL_DESTRUCTION = "THERMAL_DESTRUCTION"


@dataclass
class FittingSpec:
    """Параметры муфты, обычно считываемые со штрих-кода производителя."""

    diameter_mm: float
    resistance_cold_ohm: float
    nominal_voltage: float
    base_heating_time_s: float
    resistance_temp_coefficient: float = 0.00393  # медь/никель-хром, 1/°C


class JoulesLenzEngine:
    """
    Симулирует передачу энергии в соответствии с законом Джоуля-Ленца.
    Учитывает нелинейное изменение сопротивления спирали R(T).
    """

    REFERENCE_TEMP_C = 20.0
    MELT_TEMP_MIN_C = 210.0
    MELT_TEMP_MAX_C = 230.0

    def resistance_at_temp(self, r_cold: float, temp_c: float, alpha: float) -> float:
        """R(T) = R_cold * (1 + alpha * (T - T_ref)) — линейная модель терморезистивности."""
        return r_cold * (1 + alpha * (temp_c - self.REFERENCE_TEMP_C))

    def calculate_heat_output(self, voltage: float, resistance: float, dt: float) -> float:
        """Q = (U^2 / R) * dt, джоули за интервал dt (секунды)."""
        if resistance <= 0:
            raise ValueError("Resistance must be positive")
        return (voltage ** 2 / resistance) * dt

    def _integrate_nominal_energy(
        self, fitting: FittingSpec, dt: float = 0.1, coil_temp_rise_rate_c_per_s: float = 4.0
    ) -> float:
        """
        Энергия, реально доставляемая за base_heating_time_s при номинальном
        напряжении с учетом роста сопротивления спирали R(T) при нагреве.
        Используется как физически согласованная база для minimum_energy_for_weld:
        сопротивление растет со временем (99 факт #3), поэтому расчет "в лоб"
        по холодному R переоценивал бы доставляемую энергию.
        """
        t = 0.0
        energy = 0.0
        coil_temp = self.REFERENCE_TEMP_C
        while t < fitting.base_heating_time_s:
            resistance = self.resistance_at_temp(
                fitting.resistance_cold_ohm, coil_temp, fitting.resistance_temp_coefficient
            )
            energy += self.calculate_heat_output(fitting.nominal_voltage, resistance, dt)
            coil_temp = min(self.MELT_TEMP_MAX_C, coil_temp + coil_temp_rise_rate_c_per_s * dt)
            t += dt
        return energy

    def minimum_energy_for_weld(self, fitting: FittingSpec, ambient_temp_c: float) -> float:
        """
        Минимальная энергия для полного расплава, скорректированная на
        температуру окружающей среды: холодный воздух отбирает больше тепла.
        """
        base_energy = self._integrate_nominal_energy(fitting)
        # Компенсация: на каждый градус ниже 20°C требуется on 0.4% больше энергии
        ambient_deficit = max(0.0, self.REFERENCE_TEMP_C - ambient_temp_c)
        compensation_factor = 1.0 + ambient_deficit * 0.004
        return base_energy * compensation_factor

    def evaluate_weld_state(
        self,
        energy_accumulated: float,
        fitting: FittingSpec,
        ambient_temp_c: float,
        destruction_margin: float = 1.3,
    ) -> WeldState:
        """Определяет состояние полиэтилена: недогрев / успех / термодеструкция."""
        min_energy = self.minimum_energy_for_weld(fitting, ambient_temp_c)
        max_energy = min_energy * destruction_margin

        if energy_accumulated < min_energy:
            return WeldState.INCOMPLETE_WELD
        if energy_accumulated <= max_energy:
            return WeldState.SUCCESS
        return WeldState.THERMAL_DESTRUCTION

    def simulate_weld(
        self,
        fitting: FittingSpec,
        applied_voltage_fn,
        ambient_temp_c: float,
        duration_s: float,
        dt: float = 0.1,
        coil_temp_rise_rate_c_per_s: float = 4.0,
    ) -> dict:
        """
        Прогоняет симуляцию сварки во времени.

        applied_voltage_fn(t) -> float — функция, возвращающая напряжение на
        спирали в момент времени t (позволяет моделировать просадки сети/батареи).
        """
        t = 0.0
        energy_accumulated = 0.0
        coil_temp = self.REFERENCE_TEMP_C
        samples = []

        while t < duration_s:
            voltage = applied_voltage_fn(t)
            resistance = self.resistance_at_temp(
                fitting.resistance_cold_ohm, coil_temp, fitting.resistance_temp_coefficient
            )
            energy_step = self.calculate_heat_output(voltage, resistance, dt)
            energy_accumulated += energy_step

            coil_temp = min(
                self.MELT_TEMP_MAX_C, coil_temp + coil_temp_rise_rate_c_per_s * dt
            )

            samples.append(
                {
                    "t": round(t, 2),
                    "voltage": voltage,
                    "resistance": resistance,
                    "energy_accumulated": energy_accumulated,
                    "coil_temp": coil_temp,
                }
            )
            t += dt

        state = self.evaluate_weld_state(energy_accumulated, fitting, ambient_temp_c)

        return {
            "state": state,
            "energy_accumulated_j": energy_accumulated,
            "final_coil_temp_c": coil_temp,
            "samples": samples,
        }
