import pytest

from simulation.power_network import LiFePO4Battery, MainsSupply, BatteryDepletedError


def test_battery_ocv_at_full_charge():
    battery = LiFePO4Battery(soc=1.0)
    assert battery.open_circuit_voltage() == pytest.approx(52.8, abs=0.1)


def test_battery_voltage_sags_under_load():
    battery = LiFePO4Battery(soc=1.0)
    ocv = battery.open_circuit_voltage()
    loaded = battery.voltage_under_load(current_a=35.0)
    assert loaded < ocv


def test_battery_soc_decreases_with_draw():
    battery = LiFePO4Battery(capacity_ah=30.0, soc=1.0)
    battery.draw_current(current_a=35.0, dt_s=115)
    assert battery.soc < 1.0


def test_battery_welds_remaining_for_30ah_pack():
    battery = LiFePO4Battery(capacity_ah=30.0, soc=1.0)
    # ~45Wh per weld -> expect roughly 20-30 welds per spec requirement
    remaining = battery.welds_remaining(energy_per_weld_wh=45.0)
    assert 20 <= remaining <= 32


def test_battery_raises_when_depleted_below_cutoff():
    battery = LiFePO4Battery(capacity_ah=1.0, soc=0.12, min_soc=0.10)
    with pytest.raises(BatteryDepletedError):
        battery.draw_current(current_a=35.0, dt_s=115)


def test_battery_ocv_drops_steeply_below_15_percent_soc():
    battery = LiFePO4Battery(soc=0.05)
    ocv = battery.open_circuit_voltage()
    # Резкий спад к ~40В при глубоком истощении, ниже плато 51.2-52.8В.
    assert ocv < 51.2
    assert ocv == pytest.approx(40.0 + (0.05 / 0.15) * 11.2)


def test_instantaneous_voltage_includes_noise_term():
    mains = MainsSupply(nominal_voltage=220.0, sag_voltage=10.0, noise_amplitude=5.0)
    v = mains.instantaneous_voltage(t=0.0)
    assert v == pytest.approx(210.0)  # sin(0) == 0, no noise contribution at t=0


def test_mains_supply_safe_bounds_nominal():
    mains = MainsSupply()
    assert mains.is_within_safe_bounds() is True


def test_mains_supply_unsafe_when_sagged():
    mains = MainsSupply(sag_voltage=40.0)  # 220 - 40 = 180V < 185V
    assert mains.is_within_safe_bounds() is False


def test_mains_supply_unsafe_when_frequency_drifts():
    mains = MainsSupply(freq_drift_hz=20.0)  # 70Hz > 65Hz limit
    assert mains.is_within_safe_bounds() is False


def test_mains_supply_unsafe_when_noise_dips_below_threshold():
    # nominal - sag = 200V (сам по себе выше 185В), но амплитуда помехи 20В
    # означает, что мгновенное напряжение кратковременно проседает до 180В —
    # это должно считаться небезопасным, даже если "среднее" значение в норме.
    mains = MainsSupply(sag_voltage=20.0, noise_amplitude=20.0)
    assert mains.is_within_safe_bounds() is False


def test_mains_supply_safe_with_small_noise_within_margin():
    mains = MainsSupply(sag_voltage=0.0, noise_amplitude=5.0)  # worst case 215V
    assert mains.is_within_safe_bounds() is True
