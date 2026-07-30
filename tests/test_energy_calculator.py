import pytest

from control.energy_calculator import EnergyCalculator


def test_add_sample_accumulates_energy():
    calc = EnergyCalculator()
    calc.add_sample(voltage=39.5, current=35.0, dt_s=1.0)
    calc.add_sample(voltage=39.5, current=35.0, dt_s=1.0)
    assert calc.total_energy_j == pytest.approx(39.5 * 35.0 * 2.0)


def test_average_power_w_empty_returns_zero():
    calc = EnergyCalculator()
    assert calc.average_power_w() == 0.0


def test_average_power_w_computes_mean_power():
    calc = EnergyCalculator()
    calc.add_sample(voltage=39.5, current=35.0, dt_s=1.0)
    calc.add_sample(voltage=39.5, current=35.0, dt_s=1.0)
    assert calc.average_power_w() == pytest.approx(39.5 * 35.0)


def test_reset_clears_samples_and_energy():
    calc = EnergyCalculator()
    calc.add_sample(voltage=39.5, current=35.0, dt_s=1.0)
    calc.reset()
    assert calc.total_energy_j == 0.0
    assert calc.average_power_w() == 0.0
