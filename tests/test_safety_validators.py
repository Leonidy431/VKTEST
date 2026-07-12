import pytest

from control.safety_validator import SafetyValidator, SafetyLimits


@pytest.fixture
def validator():
    return SafetyValidator()


def test_pre_start_passes_with_nominal_conditions(validator):
    result = validator.check_pre_start(
        input_voltage=220.0, mains_freq_hz=50.0, ambient_temp_c=15.0, battery_voltage=50.0
    )
    assert result is None


def test_pre_start_fails_low_voltage(validator):
    result = validator.check_pre_start(
        input_voltage=180.0, mains_freq_hz=50.0, ambient_temp_c=15.0
    )
    assert result is not None
    assert result.code == "LOW_INPUT_VOLTAGE"


def test_pre_start_fails_bad_frequency(validator):
    result = validator.check_pre_start(
        input_voltage=220.0, mains_freq_hz=70.0, ambient_temp_c=15.0
    )
    assert result.code == "FREQUENCY_OUT_OF_RANGE"


def test_pre_start_fails_too_cold(validator):
    result = validator.check_pre_start(
        input_voltage=220.0, mains_freq_hz=50.0, ambient_temp_c=-25.0
    )
    assert result.code == "AMBIENT_TOO_COLD"


def test_pre_start_fails_low_battery(validator):
    result = validator.check_pre_start(
        input_voltage=220.0, mains_freq_hz=50.0, ambient_temp_c=15.0, battery_voltage=40.0
    )
    assert result.code == "BATTERY_LOW"


def test_during_weld_detects_open_circuit(validator):
    result = validator.check_during_weld(current_a=0.0, heatsink_temp_c=40.0)
    assert result.code == "OPEN_CIRCUIT"


def test_during_weld_detects_short_circuit(validator):
    result = validator.check_during_weld(current_a=150.0, heatsink_temp_c=40.0)
    assert result.code == "SHORT_CIRCUIT"


def test_during_weld_detects_critical_overheat(validator):
    result = validator.check_during_weld(current_a=35.0, heatsink_temp_c=85.0)
    assert result.code == "OVERHEAT_CRITICAL"


def test_during_weld_passes_nominal(validator):
    result = validator.check_during_weld(current_a=35.0, heatsink_temp_c=45.0)
    assert result is None


def test_should_derate_in_warning_band(validator):
    assert validator.should_derate(75.0) is True


def test_should_not_derate_below_threshold(validator):
    assert validator.should_derate(50.0) is False
