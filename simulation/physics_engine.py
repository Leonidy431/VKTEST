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
    base_cooling_time_s: float = 1200.0  # 20 мин — типовое время остывания (99 факт #93)


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
        self,
        fitting: FittingSpec,
        duration_s: float,
        dt: float = 0.1,
        coil_temp_rise_rate_c_per_s: float = 4.0,
    ) -> float:
        """
        Энергия, реально доставляемая за duration_s при номинальном напряжении
        с учетом роста сопротивления спирали R(T) при нагреве. Используется
        как физически согласованная база для minimum_energy_for_weld:
        сопротивление растет со временем (99 факт #3) и насыщается на
        MELT_TEMP_MAX_C, поэтому расчет "в лоб" по холодному R переоценивал
        бы доставляемую энергию, а линейное масштабирование по времени
        недооценивало бы влияние насыщения R(T).
        """
        if dt <= 0:
            raise ValueError("dt must be positive")
        t = 0.0
        energy = 0.0
        coil_temp = self.REFERENCE_TEMP_C
        while t < duration_s:
            resistance = self.resistance_at_temp(
                fitting.resistance_cold_ohm, coil_temp, fitting.resistance_temp_coefficient
            )
            energy += self.calculate_heat_output(fitting.nominal_voltage, resistance, dt)
            coil_temp = min(self.MELT_TEMP_MAX_C, coil_temp + coil_temp_rise_rate_c_per_s * dt)
            t += dt
        return energy

    def minimum_energy_for_weld(self, fitting: FittingSpec, heating_time_s: float) -> float:
        """
        Минимальная энергия для полного расплава — прямой интеграл по
        фактическому времени нагрева (heating_time_s), уже скорректированному
        на температуру окружающей среды в TemperatureCompensator.

        Ранее ambient-компенсация энергии считалась отдельным линейным
        коэффициентом, независимым от компенсации времени в
        control/temperature_compensator.py. Из-за насыщения R(T) на
        MELT_TEMP_MAX_C энергия НЕ растет линейно со временем нагрева, из-за
        чего два независимых коэффициента расходились: физически корректная
        сварка (100% номинального напряжения на протяжении всего
        скомпенсированного времени) в диапазоне +0..+19°C ошибочно
        классифицировалась как INCOMPLETE_WELD. Интеграция напрямую по
        heating_time_s устраняет расхождение по построению — обе величины
        теперь получены из одной и той же длительности.
        """
        return self._integrate_nominal_energy(fitting, heating_time_s)

    def evaluate_weld_state(
        self,
        energy_accumulated: float,
        fitting: FittingSpec,
        heating_time_s: float,
        destruction_margin: float = 1.3,
    ) -> WeldState:
        """Определяет состояние полиэтилена: недогрев / успех / термодеструкция."""
        min_energy = self.minimum_energy_for_weld(fitting, heating_time_s)
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
        duration_s: float,
        dt: float = 0.1,
        coil_temp_rise_rate_c_per_s: float = 4.0,
    ) -> dict:
        """
        Прогоняет симуляцию сварки во времени.

        applied_voltage_fn(t) -> float — функция, возвращающая напряжение на
        спирали в момент времени t (позволяет моделировать просадки сети/батареи).
        duration_s — фактическое время нагрева, уже скорректированное на
        температуру окружающей среды вызывающей стороной (см.
        control.temperature_compensator.TemperatureCompensator), если требуется.
        """
        if dt <= 0:
            raise ValueError("dt must be positive")
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

        state = self.evaluate_weld_state(energy_accumulated, fitting, duration_s)

        return {
            "state": state,
            "energy_accumulated_j": energy_accumulated,
            "final_coil_temp_c": coil_temp,
            "samples": samples,
        }
