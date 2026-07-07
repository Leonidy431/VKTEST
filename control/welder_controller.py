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
    ) -> WeldResult:
        sm = self.state_machine
        sm.transition_to(WeldingState.VALIDATE_CODE)

        pre_start_violation = self.safety.check_pre_start(
            input_voltage, mains_freq_hz, ambient_temp_c, battery_voltage
        )
        if pre_start_violation:
            sm.raise_error(pre_start_violation.message)
            return WeldResult(False, sm.state, 0.0, 0.0, pre_start_violation.message)

        sm.transition_to(WeldingState.TEST_PULSE)
        resistance_delta = abs(measured_resistance - fitting.resistance_cold_ohm) / fitting.resistance_cold_ohm
        if resistance_delta > 0.10:
            reason = (
                f"Сопротивление {measured_resistance:.3f}Ом отличается от заявленного "
                f"{fitting.resistance_cold_ohm:.3f}Ом на {resistance_delta:.1%}"
            )
            sm.raise_error(reason)
            return WeldResult(False, sm.state, 0.0, 0.0, reason)

        sm.transition_to(WeldingState.PRE_WELD)

        heating_time = self.temp_compensator.compensate_heating_time(
            fitting.base_heating_time_s, ambient_temp_c
        )

        sm.transition_to(WeldingState.HEATING)
        self.pid.reset()
        self.energy_calc.reset()

        t = 0.0
        while t < heating_time:
            voltage = get_voltage_reading(t)
            current = get_current_reading(t)
            heatsink_temp = get_heatsink_temp(t)

            fault = self.safety.check_during_weld(current, heatsink_temp)
            if fault:
                sm.raise_error(fault.message)
                return WeldResult(
                    False, sm.state, self.energy_calc.total_energy_j, t, fault.message
                )

            self.energy_calc.add_sample(voltage, current, dt)
            self.pid.update(voltage, dt)
            t += dt

        sm.transition_to(WeldingState.COOLING_WAIT)
        sm.transition_to(WeldingState.DONE_SUCCESS)

        weld_state = self.physics.evaluate_weld_state(
            self.energy_calc.total_energy_j, fitting, ambient_temp_c
        )

        result = WeldResult(
            success=(weld_state == WeldState.SUCCESS),
            final_state=sm.state,
            energy_delivered_j=self.energy_calc.total_energy_j,
            heating_time_s=heating_time,
        )
        sm.transition_to(WeldingState.IDLE)
        return result
