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
        base_cooling_time_s=10,  # укорочено для скорости теста
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


def test_overcurrent_during_heating_aborts(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 115.0,  # выше рабочего максимума 110А
        get_heatsink_temp=lambda t: 40.0,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR
    assert "110" in result.error_reason


def test_rejects_nonpositive_dt(fitting):
    controller = WelderController()
    with pytest.raises(ValueError):
        controller.run_weld_cycle(
            fitting=fitting,
            measured_resistance=1.13,
            ambient_temp_c=20.0,
            input_voltage=220.0,
            mains_freq_hz=50.0,
            get_voltage_reading=lambda t: 39.5,
            get_current_reading=lambda t: 35.0,
            get_heatsink_temp=lambda t: 40.0,
            dt=0.0,
        )


def test_derate_engages_when_heatsink_hot(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 75.0,  # в полосе derating (70, 80]
        dt=0.1,
    )
    assert result.was_derated is True
    assert result.final_state == WeldingState.DONE_SUCCESS  # derating != авария


def test_no_derate_when_heatsink_nominal(fitting):
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
        dt=0.1,
    )
    assert result.was_derated is False


def test_successful_weld_reports_compensated_cooling_time(fitting):
    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,  # reference temp, no compensation
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
    )
    assert result.cooling_time_s == pytest.approx(fitting.base_cooling_time_s)


def test_premature_restart_blocked_during_cooling(fitting):
    controller = WelderController()
    first = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
    )
    assert first.success is True

    # Попытка начать новую сварку немедленно (elapsed_since_last_weld_s не
    # указан -> по умолчанию бесконечность в тестах ниже не действует, здесь
    # явно передаем 0, т.к. остывание предыдущего соединения не завершено).
    blocked = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
        elapsed_since_last_weld_s=0.0,
    )
    assert blocked.success is False
    assert blocked.final_state == WeldingState.ERROR
    assert "Охлаждение" in blocked.error_reason

    # После истечения требуемого времени остывания — сварка разрешена вновь.
    allowed = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
        elapsed_since_last_weld_s=fitting.base_cooling_time_s,
    )
    assert allowed.success is True


def test_exception_during_heating_transitions_to_error_not_stranded(fitting):
    def raising_current_reading(t):
        raise RuntimeError("датчик тока отвалился")

    controller = WelderController()
    result = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=raising_current_reading,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
    )
    assert result.success is False
    assert result.final_state == WeldingState.ERROR
    assert "исключение" in result.error_reason.lower()
    # Машина состояний не должна оставаться "застрявшей" в HEATING —
    # контроллер обязан быть готов принять следующий цикл без падения
    # InvalidTransitionError (найдено аудитом).
    assert controller.state_machine.state == WeldingState.IDLE


def test_controller_reusable_after_any_failure(fitting):
    """
    Регрессия: раньше ЛЮБОЙ путь отказа (не только необработанное
    исключение) оставлял машину состояний в ERROR без сброса, и повторный
    вызов run_weld_cycle на том же контроллере падал с
    InvalidTransitionError, потому что VALIDATE_CODE недостижим из ERROR.
    """
    controller = WelderController()
    failed = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=150.0,  # ниже 185В -> отказ еще до нагрева
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
    )
    assert failed.final_state == WeldingState.ERROR

    # Второй вызов на том же экземпляре не должен падать.
    second = controller.run_weld_cycle(
        fitting=fitting,
        measured_resistance=1.13,
        ambient_temp_c=20.0,
        input_voltage=220.0,
        mains_freq_hz=50.0,
        get_voltage_reading=lambda t: 39.5,
        get_current_reading=lambda t: 35.0,
        get_heatsink_temp=lambda t: 40.0,
        dt=0.1,
    )
    assert second.success is True
