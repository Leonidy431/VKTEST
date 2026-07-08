"""
Tests для алгоритмов beamforming.

Проверяет:
- Расчет фазовых весов
- Направление луча
- Расчет усиления диаграммы направленности
- Сканирование луча
"""

import pytest
import math

from phased_array.config import Config
from phased_array.beamforming import BeamForming, BeamPattern


class TestBeamFormingInit:
    """Тесты инициализации BeamForming."""

    def test_creation(self):
        """Создание экземпляра BeamForming."""
        bf = BeamForming()
        assert bf.num_elements == Config.NUM_ELEMENTS
        assert bf.element_spacing_lambda == Config.ELEMENT_SPACING_LAMBDA

    def test_default_beam_pattern(self):
        """Проверка начального паттерна луча."""
        bf = BeamForming()
        assert bf.current_beam.azimuth_deg == 0.0
        assert bf.current_beam.elevation_deg == 0.0
        assert bf.current_beam.gain_dbi == Config.GAIN_DBI

    def test_phase_weights_initialization(self):
        """Проверка инициализации фазовых весов."""
        bf = BeamForming()
        assert len(bf.phase_weights) == Config.NUM_ELEMENTS
        assert all(w == 0.0 for w in bf.phase_weights)


class TestBeamFormingPointBeam:
    """Тесты направления луча."""

    def test_point_beam_center(self):
        """Направление луча в центр (0°, 0°)."""
        bf = BeamForming()
        beam = bf.point_beam(0.0, 0.0)
        assert beam.azimuth_deg == 0.0
        assert beam.elevation_deg == 0.0

    def test_point_beam_azimuth_90(self):
        """Направление луча на 90° азимута."""
        bf = BeamForming()
        beam = bf.point_beam(90.0, 0.0)
        assert beam.azimuth_deg == 90.0

    def test_point_beam_azimuth_360_wrap(self):
        """Обертывание азимута 360° → 0°."""
        bf = BeamForming()
        beam = bf.point_beam(360.0, 0.0)
        assert beam.azimuth_deg % 360.0 == 0.0

    def test_point_beam_elevation_valid(self):
        """Проверка ограничений возвышения (-90…+90°)."""
        bf = BeamForming()
        # Попытка установить > +90°
        beam = bf.point_beam(0.0, 100.0)
        assert beam.elevation_deg == 90.0

        # Попытка установить < -90°
        beam = bf.point_beam(0.0, -100.0)
        assert beam.elevation_deg == -90.0

    def test_point_beam_updates_current_beam(self):
        """Проверка обновления текущего луча."""
        bf = BeamForming()
        beam1 = bf.point_beam(45.0, 30.0)
        assert bf.current_beam.azimuth_deg == 45.0
        assert bf.current_beam.elevation_deg == 30.0

        beam2 = bf.point_beam(90.0, 0.0)
        assert bf.current_beam.azimuth_deg == 90.0


class TestBeamFormingPhaseWeights:
    """Тесты расчета фазовых весов."""

    def test_phase_weights_calculated(self):
        """Проверка что фазовые веса рассчитаны."""
        bf = BeamForming()
        bf.point_beam(45.0, 0.0)
        phase_weights = bf.get_phase_weights()
        # Веса должны быть в диапазоне [0, 360)
        assert all(0.0 <= w < 360.0 for w in phase_weights)

    def test_phase_weights_symmetry(self):
        """Проверка симметрии фазовых весов."""
        bf = BeamForming()
        # Луч в центр должен давать примерно нулевые фазовые сдвиги
        bf.point_beam(0.0, 0.0)
        weights = bf.get_phase_weights()
        # Для линейного массива с направлением в центр
        # первый и последний элементы должны иметь противоположные фазовые сдвиги
        assert abs(weights[0]) < 10.0 or abs(weights[0] - 360.0) < 10.0

    def test_phase_weights_different_angles(self):
        """Проверка что разные углы дают разные фазовые веса."""
        bf = BeamForming()
        bf.point_beam(0.0, 0.0)
        weights_0 = bf.get_phase_weights()

        bf.point_beam(45.0, 0.0)
        weights_45 = bf.get_phase_weights()

        assert weights_0 != weights_45


class TestBeamFormingGainCalculation:
    """Тесты расчета усиления."""

    def test_calculate_gain_center(self):
        """Усиление в центре луча (максимум)."""
        bf = BeamForming()
        bf.point_beam(0.0, 0.0)
        gain_center = bf.calculate_gain_at_angle(0.0, 0.0)
        # В центре луча усиление максимально
        assert gain_center > 0

    def test_calculate_gain_different_angles(self):
        """Усиление уменьшается при отходе от центра луча."""
        bf = BeamForming()
        bf.point_beam(0.0, 0.0)
        gain_center = bf.calculate_gain_at_angle(0.0, 0.0)
        gain_offset = bf.calculate_gain_at_angle(30.0, 0.0)
        # Усиление в стороне от луча должно быть меньше
        assert gain_offset <= gain_center

    def test_calculate_gain_range(self):
        """Проверка диапазона усиления."""
        bf = BeamForming()
        for angle in range(0, 360, 45):
            gain = bf.calculate_gain_at_angle(float(angle), 0.0)
            # Усиление должно быть в разумном диапазоне
            assert -30 < gain < 20


class TestBeamFormingScan:
    """Тесты сканирования луча."""

    def test_scan_beam_pattern(self):
        """Сканирование луча по азимуту."""
        bf = BeamForming()
        patterns = bf.scan_beam_pattern(step_deg=45.0)
        # Для 360° / 45° = 8 направлений
        assert len(patterns) == 8
        assert all(isinstance(p, BeamPattern) for p in patterns)

    def test_scan_beam_pattern_step_10(self):
        """Сканирование с шагом 10°."""
        bf = BeamForming()
        patterns = bf.scan_beam_pattern(step_deg=10.0)
        # 360 / 10 = 36 направлений
        assert len(patterns) == 36

    def test_scan_beam_pattern_azimuths(self):
        """Проверка покрытия азимутов при сканировании."""
        bf = BeamForming()
        patterns = bf.scan_beam_pattern(step_deg=90.0)
        azimuths = [p.azimuth_deg for p in patterns]
        assert 0.0 in azimuths
        assert 90.0 in azimuths
        assert 180.0 in azimuths
        assert 270.0 in azimuths


class TestBeamFormingWeightsCopy:
    """Тесты получения копий весов."""

    def test_get_phase_weights_returns_copy(self):
        """Получить фазовые веса должно возвращать копию, не ссылку."""
        bf = BeamForming()
        bf.point_beam(45.0, 0.0)
        weights1 = bf.get_phase_weights()
        weights2 = bf.get_phase_weights()
        # Должны быть равны но не одно и то же объект
        assert weights1 == weights2
        assert weights1 is not weights2

    def test_get_amplitude_weights_returns_copy(self):
        """Получить амплитудные веса должно возвращать копию."""
        bf = BeamForming()
        weights1 = bf.get_amplitude_weights()
        weights2 = bf.get_amplitude_weights()
        assert weights1 is not weights2
        assert len(weights1) == Config.NUM_ELEMENTS


class TestBeamFormingRepr:
    """Тест строкового представления."""

    def test_repr(self):
        """Проверка __repr__."""
        bf = BeamForming()
        bf.point_beam(45.0, 30.0)
        repr_str = repr(bf)
        assert 'BeamForming' in repr_str
        assert '45.0' in repr_str
        assert '30.0' in repr_str
