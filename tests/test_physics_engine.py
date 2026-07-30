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


def test_longer_heating_time_requires_more_energy(engine, fitting):
    # Более длительный нагрев (как после ambient-компенсации в холод) должен
    # физически согласованно поднимать порог минимальной энергии — обе
    # величины теперь выводятся из одной и той же длительности heating_time_s.
    energy_nominal = engine.minimum_energy_for_weld(fitting, heating_time_s=fitting.base_heating_time_s)
    energy_extended = engine.minimum_energy_for_weld(
        fitting, heating_time_s=fitting.base_heating_time_s * 1.2
    )
    assert energy_extended > energy_nominal


def test_evaluate_weld_state_incomplete(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, heating_time_s=fitting.base_heating_time_s)
    state = engine.evaluate_weld_state(min_energy * 0.5, fitting, heating_time_s=fitting.base_heating_time_s)
    assert state == WeldState.INCOMPLETE_WELD


def test_evaluate_weld_state_success(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, heating_time_s=fitting.base_heating_time_s)
    state = engine.evaluate_weld_state(min_energy * 1.1, fitting, heating_time_s=fitting.base_heating_time_s)
    assert state == WeldState.SUCCESS


def test_evaluate_weld_state_thermal_destruction(engine, fitting):
    min_energy = engine.minimum_energy_for_weld(fitting, heating_time_s=fitting.base_heating_time_s)
    state = engine.evaluate_weld_state(min_energy * 2.0, fitting, heating_time_s=fitting.base_heating_time_s)
    assert state == WeldState.THERMAL_DESTRUCTION


def test_simulate_weld_stable_voltage_succeeds(engine, fitting):
    result = engine.simulate_weld(
        fitting=fitting,
        applied_voltage_fn=lambda t: 39.5,
        duration_s=fitting.base_heating_time_s,
        dt=1.0,
    )
    assert result["state"] == WeldState.SUCCESS


def test_simulate_weld_undervoltage_causes_incomplete_weld(engine, fitting):
    # Просадка до 34В (как в примере критика: 190В сеть -> 34В на выходе)
    result = engine.simulate_weld(
        fitting=fitting,
        applied_voltage_fn=lambda t: 34.0,
        duration_s=fitting.base_heating_time_s,
        dt=1.0,
    )
    assert result["state"] == WeldState.INCOMPLETE_WELD


def test_integrate_nominal_energy_rejects_nonpositive_dt(engine, fitting):
    with pytest.raises(ValueError):
        engine._integrate_nominal_energy(fitting, duration_s=fitting.base_heating_time_s, dt=0.0)


def test_simulate_weld_rejects_nonpositive_dt(engine, fitting):
    with pytest.raises(ValueError):
        engine.simulate_weld(
            fitting=fitting,
            applied_voltage_fn=lambda t: 39.5,
            duration_s=fitting.base_heating_time_s,
            dt=0.0,
        )


def test_full_pipeline_succeeds_across_cold_ambient_range(fitting):
    """
    Регрессия для найденного критиком дефекта: до фикса физически безупречная
    сварка (100% номинального напряжения на протяжении всего скомпенсированного
    времени нагрева) ошибочно давала INCOMPLETE_WELD для ambient в 0..+19°C,
    потому что energy-порог и time-компенсация считались независимо и
    расходились из-за насыщения R(T).

    Ток моделируется через тот же R(T), что и внутри JoulesLenzEngine
    (спираль греется, сопротивление растет, ток при постоянном номинальном
    напряжении падает) — иначе тест сравнивал бы физически несогласованные
    величины: наивный "ток по холодному R" все время сварки завышает
    доставляемую энергию относительно того, что реально проинтегрирует
    evaluate_weld_state, и ошибочно попадает в THERMAL_DESTRUCTION.
    """
    from control.temperature_compensator import TemperatureCompensator
    from control.welder_controller import WelderController

    engine = JoulesLenzEngine()

    def resistance_at_t(t: float) -> float:
        coil_temp = min(engine.MELT_TEMP_MAX_C, engine.REFERENCE_TEMP_C + 4.0 * t)
        return engine.resistance_at_temp(
            fitting.resistance_cold_ohm, coil_temp, fitting.resistance_temp_coefficient
        )

    compensator = TemperatureCompensator()
    for ambient in (20.0, 15.0, 10.0, 5.0, 0.0, -5.0, -10.0, -20.0):
        heating_time = compensator.compensate_heating_time(fitting.base_heating_time_s, ambient)
        controller = WelderController()
        result = controller.run_weld_cycle(
            fitting=fitting,
            measured_resistance=fitting.resistance_cold_ohm,
            ambient_temp_c=ambient,
            input_voltage=220.0,
            mains_freq_hz=50.0,
            get_voltage_reading=lambda t: fitting.nominal_voltage,
            get_current_reading=lambda t: fitting.nominal_voltage / resistance_at_t(t),
            get_heatsink_temp=lambda t: 40.0,
            dt=0.1,
        )
        assert result.success, f"ambient={ambient}: expected SUCCESS, heating_time={heating_time:.1f}s"
