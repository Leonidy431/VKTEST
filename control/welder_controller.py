"""
Главный контроллер: связывает конечный автомат, ПИД-регулятор, физический
движок, безопасность и температурную компенсацию в единый процесс сварки.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from simulation.physics_engine import FittingSpec, JoulesLenzEngine, WeldState
from simulation.pid_simulator import PIDVoltageRegulator

from .state_machine import WeldingState, WeldingStateMachine
from .energy_calculator import EnergyCalculator
from .temperature_compensator import TemperatureCompensator
from .safety_validator import SafetyValidator, SafetyViolation


@dataclass
class WeldResult:
    success: bool
    final_state: WeldingState
    energy_delivered_j: float
    heating_time_s: float
    error_reason: Optional[str] = None
    cooling_time_s: float = 0.0
    was_derated: bool = False


# 99 факт #17: снижение доставляемой мощности до этой доли от номинала,
# пока температура радиатора находится в полосе derating (see should_derate).
DERATE_POWER_FRACTION = 0.7


class WelderController:
    def __init__(
        self,
        physics_engine: Optional[JoulesLenzEngine] = None,
        pid: Optional[PIDVoltageRegulator] = None,
        safety: Optional[SafetyValidator] = None,
        temp_compensator: Optional[TemperatureCompensator] = None,
    ) -> None:
        self.physics = physics_engine or JoulesLenzEngine()
        self.pid = pid or PIDVoltageRegulator()
        self.safety = safety or SafetyValidator()
        self.temp_compensator = temp_compensator or TemperatureCompensator()
        self.state_machine = WeldingStateMachine()
        self.energy_calc = EnergyCalculator()
        # Время, оставшееся до конца обязательного остывания предыдущей
        # сварки (99 факт #93) — 0, если остывание не требуется/завершено.
        self._required_cooling_s = 0.0

    def _abort(self, reason: str) -> WeldingState:
        """
        Переводит машину состояний в ERROR, фиксирует итоговое состояние для
        отчета в WeldResult, затем возвращает машину в IDLE, готовую к
        следующему циклу.

        Без этого сброса контроллер после ЛЮБОГО отказа (низкое напряжение,
        несовпадение сопротивления, авария во время нагрева, необработанное
        исключение) оставался бы в ERROR, и следующий вызов run_weld_cycle
        на том же экземпляре падал бы с InvalidTransitionError, так как
        VALIDATE_CODE недостижим из ERROR (только IDLE). Комментарий в
        test_successful_weld_cycle утверждал, что состояние "отдельно
        возвращается в IDLE внутри run_weld_cycle" — это было верно только
        для пути успеха; все пути отказа этот сброс пропускали.
        """
        self.state_machine.raise_error(reason)
        reported_state = self.state_machine.state
        self.state_machine.transition_to(WeldingState.IDLE)
        return reported_state

    def run_weld_cycle(
        self,
        fitting: FittingSpec,
        measured_resistance: float,
        ambient_temp_c: float,
        input_voltage: float,
        mains_freq_hz: float,
        get_voltage_reading: Callable[[float], float],
        get_current_reading: Callable[[float], float],
        get_heatsink_temp: Callable[[float], float],
        battery_voltage: Optional[float] = None,
        dt: float = 0.1,
        elapsed_since_last_weld_s: float = float("inf"),
    ) -> WeldResult:
        if dt <= 0:
            raise ValueError("dt must be positive")

        sm = self.state_machine

        if self._required_cooling_s > 0:
            if elapsed_since_last_weld_s < self._required_cooling_s:
                remaining = self._required_cooling_s - elapsed_since_last_weld_s
                reason = f"Охлаждение предыдущего соединения не завершено: осталось {remaining:.0f}с"
                reported = self._abort(reason)
                return WeldResult(False, reported, 0.0, 0.0, reason)
            self._required_cooling_s = 0.0

        sm.transition_to(WeldingState.VALIDATE_CODE)

        pre_start_violation = self.safety.check_pre_start(
            input_voltage, mains_freq_hz, ambient_temp_c, battery_voltage
        )
        if pre_start_violation:
            reported = self._abort(pre_start_violation.message)
            return WeldResult(False, reported, 0.0, 0.0, pre_start_violation.message)

        sm.transition_to(WeldingState.TEST_PULSE)
        resistance_delta = abs(measured_resistance - fitting.resistance_cold_ohm) / fitting.resistance_cold_ohm
        if resistance_delta > 0.10:
            reason = (
                f"Сопротивление {measured_resistance:.3f}Ом отличается от заявленного "
                f"{fitting.resistance_cold_ohm:.3f}Ом на {resistance_delta:.1%}"
            )
            reported = self._abort(reason)
            return WeldResult(False, reported, 0.0, 0.0, reason)

        sm.transition_to(WeldingState.PRE_WELD)

        heating_time = self.temp_compensator.compensate_heating_time(
            fitting.base_heating_time_s, ambient_temp_c
        )

        sm.transition_to(WeldingState.HEATING)
        self.pid.reset()
        self.energy_calc.reset()
        nominal_target_voltage = self.pid.target_voltage
        derated_target_voltage = nominal_target_voltage * (DERATE_POWER_FRACTION ** 0.5)
        was_derated = False

        t = 0.0
        try:
            while t < heating_time:
                voltage = get_voltage_reading(t)
                current = get_current_reading(t)
                heatsink_temp = get_heatsink_temp(t)

                fault = self.safety.check_during_weld(current, heatsink_temp)
                if fault:
                    reported = self._abort(fault.message)
                    return WeldResult(
                        False, reported, self.energy_calc.total_energy_j, t, fault.message
                    )

                if self.safety.should_derate(heatsink_temp):
                    was_derated = True
                    self.pid.target_voltage = derated_target_voltage
                else:
                    self.pid.target_voltage = nominal_target_voltage

                self.energy_calc.add_sample(voltage, current, dt)
                self.pid.update(voltage, dt)
                t += dt
        except Exception as exc:
            reason = f"Необработанное исключение во время нагрева: {exc}"
            reported = self._abort(reason)
            return WeldResult(
                False, reported, self.energy_calc.total_energy_j, t, reason, was_derated=was_derated
            )
        finally:
            self.pid.target_voltage = nominal_target_voltage

        sm.transition_to(WeldingState.COOLING_WAIT)

        cooling_time = self.temp_compensator.compensate_cooling_time(
            fitting.base_cooling_time_s, ambient_temp_c
        )
        self._required_cooling_s = cooling_time

        sm.transition_to(WeldingState.DONE_SUCCESS)

        weld_state = self.physics.evaluate_weld_state(
            self.energy_calc.total_energy_j, fitting, heating_time
        )

        result = WeldResult(
            success=(weld_state == WeldState.SUCCESS),
            final_state=sm.state,
            energy_delivered_j=self.energy_calc.total_energy_j,
            heating_time_s=heating_time,
            cooling_time_s=cooling_time,
            was_derated=was_derated,
        )
        sm.transition_to(WeldingState.IDLE)
        return result
