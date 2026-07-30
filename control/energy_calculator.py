"""Вычисление переданной энергии в реальном времени по измерениям U/I."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class EnergySample:
    t_s: float
    voltage: float
    current: float


@dataclass
class EnergyCalculator:
    """
    Интегрирует мгновенную мощность P = U * I по времени, используя
    True RMS выборки не реже 1 кГц (99 факт #29-30).
    """

    samples: List[EnergySample] = field(default_factory=list)
    _energy_j: float = 0.0
    _elapsed_s: float = 0.0

    def add_sample(self, voltage: float, current: float, dt_s: float) -> float:
        power_w = voltage * current
        self._energy_j += power_w * dt_s
        self._elapsed_s += dt_s
        # t_s — суммарное время на момент ЭТОЙ выборки (после ее учета), а не
        # len(samples)*dt_s: последнее корректно только для равномерного dt_s
        # и к тому же занижает итоговую длительность на один интервал,
        # завышая average_power_w (найдено при написании тестов на покрытие).
        self.samples.append(EnergySample(t_s=self._elapsed_s, voltage=voltage, current=current))
        return self._energy_j

    @property
    def total_energy_j(self) -> float:
        return self._energy_j

    def average_power_w(self) -> float:
        if not self.samples or self._elapsed_s <= 0:
            return 0.0
        return self._energy_j / self._elapsed_s

    def reset(self) -> None:
        self.samples.clear()
        self._energy_j = 0.0
        self._elapsed_s = 0.0
