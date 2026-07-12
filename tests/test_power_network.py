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


def test_mains_supply_safe_bounds_nominal():
    mains = MainsSupply()
    assert mains.is_within_safe_bounds() is True


def test_mains_supply_unsafe_when_sagged():
    mains = MainsSupply(sag_voltage=40.0)  # 220 - 40 = 180V < 185V
    assert mains.is_within_safe_bounds() is False


def test_mains_supply_unsafe_when_frequency_drifts():
    mains = MainsSupply(freq_drift_hz=20.0)  # 70Hz > 65Hz limit
    assert mains.is_within_safe_bounds() is False
