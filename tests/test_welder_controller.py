import pytest

from control.welder_controller import WelderController
from control.state_machine import WeldingState
from simulation.physics_engine import FittingSpec


@pytest.fixture
def fitting():
    return FittingSpec(
        diameter_mm=32,
        resistance_cold_ohm=1.13,
        nominal_voltage=39.5,
        base_heating_time_s=5,  # укорочено для скорости теста
    )


def test_successful_weld_cycle(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        battery_voltage=50.0,
        dt=0.1,
    )
    # final_state отражает исход цикла (DONE_SUCCESS/ERROR); машина состояний
    # отдельно возвращается в IDLE внутри run_weld_cycle, готовая к следующей сварке.
    assert result.final_state == WeldingState.DONE_SUCCESS
    assert result.success is True
    assert result.error_reason is None


def test_low_input_voltage_aborts_before_heating(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=150.0,  # ниже 185В
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR
    assert "185" in result.error_reason or "Входное" in result.error_reason


def test_resistance_mismatch_aborts_at_test_pulse(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=0.200,  # >10% отличие от 1.13
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR


def test_open_circuit_during_heating_aborts(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 0.0,  # обрыв цепи
        get_heatsink_temp=lambda t: 40.0,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR
    assert "обрыв" in result.error_reason.lower() or "open" in result.error_reason.lower() or result.error_reason


def test_short_circuit_during_heating_aborts(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 150.0,  # короткое замыкание
        get_heatsink_temp=lambda t: 40.0,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR
