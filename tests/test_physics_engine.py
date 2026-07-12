import pytest

from simulation.physics_engine import FittingSpec, JoulesLenzEngine, WeldState


@pytest.fixture
def fitting():
    return FittingSpec(
        diameter_mm=32,
        resistance_cold_ohm=1.13,
        nominal_voltage=39.5,
        base_heating_time_s=115,
    )


@pytest.fixture
def engine():
    return JoulesLenzEngine()


def test_calculate_heat_output_basic(engine):
    # Q = U^2/R * t = 39.5^2 / 1.13 * 1 = 12191.9...
    q = engine.calculate_heat_output(voltage=39.5, resistance=1.13, dt=1.0)
    assert q == pytest.approx(39.5 ** 2 / 1.13, rel=1e-6)


def test_calculate_heat_output_rejects_zero_resistance(engine):
    with pytest.raises(ValueError):
        engine.calculate_heat_output(voltage=39.5, resistance=0.0, dt=1.0)


def test_resistance_increases_with_temperature(engine):
    r_cold = engine.resistance_at_temp(1.13, 20.0, 0.00393)
    r_hot = engine.resistance_at_temp(1.13, 220.0, 0.00393)
    assert r_hot > r_cold


def test_lower_ambient_temp_requires_more_energy(engine, fitting):
    energy_warm = engine.minimum_energy_for_weld(fitting, ambient_temp_c=20.0)
    energy_cold = engine.minimum_energy_for_weld(fitting, ambient_temp_c=-10.0)
    assert energy_cold > energy_warm


def test_evaluate_weld_state_incomplete(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, ambient_temp_c=20.0)
    state = engine.evaluate_weld_state(min_energy * 0.5, fitting, ambient_temp_c=20.0)
    assert state == WeldState.INCOMPLETE_WELD


def test_evaluate_weld_state_success(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, ambient_temp_c=20.0)
    state = engine.evaluate_weld_state(min_energy * 1.1, fitting, ambient_temp_c=20.0)
    assert state == WeldState.SUCCESS


def test_evaluate_weld_state_thermal_destruction(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, ambient_temp_c=20.0)
    state = engine.evaluate_weld_state(min_energy * 2.0, fitting, ambient_temp_c=20.0)
    assert state == WeldState.THERMAL_DESTRUCTION


def test_simulate_weld_stable_voltage_succeeds(engine, fitting):
    result = engine.simulate_weld(
        fitting=fitting,
        applied_voltage_fn=lambda t: 39.5,
        ambient_temp_c=20.0,
        duration_s=fitting.base_heating_time_s,
        dt=1.0,
    )
    assert result["state"] == WeldState.SUCCESS


def test_simulate_weld_undervoltage_causes_incomplete_weld(engine, fitting):
    # Просадка до 34В (как в примере критика: 190В сеть -> 34В на выходе)
    result = engine.simulate_weld(
        fitting=fitting,
        applied_voltage_fn=lambda t: 34.0,
        ambient_temp_c=20.0,
        duration_s=fitting.base_heating_time_s,
        dt=1.0,
    )
    assert result["state"] == WeldState.INCOMPLETE_WELD
