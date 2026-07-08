"""
Алгоритмы формирования луча (Beamforming) для ФАР.

MVP версия:
- Статический луч (на центральную частоту)
- Поиск оптимального луча (beam steering)
- Компенсация многолучевого распространения (будущая фаза)

Фаза 2: Адаптивное управление фазой через фазовращатели
Фаза 3: Цифровое DBF на FPGA с матрицей весов
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Tuple

from .config import Config


@dataclass
class BeamPattern:
    """Паттерн диаграммы направленности."""
    azimuth_deg: float  # Азимут в градусах (0-360°)
    elevation_deg: float  # Возвышение в градусах (-90 до +90°)
    gain_dbi: float  # Усиление в dBi относительно изотропного
    sidelobe_level_db: float  # Уровень боковых лепестков


class BeamForming:
    """
    Управление формированием луча для массива антенн.

    MVP использует встроенное beamforming в чипсете.
    Фазовращатели управляются через SPI (будущие фазы).
    """

    def __init__(self, num_elements: int = Config.NUM_ELEMENTS,
                 element_spacing_lambda: float = Config.ELEMENT_SPACING_LAMBDA):
        """
        Инициализация beamforming модуля.

        Args:
            num_elements: Количество элементов в массиве
            element_spacing_lambda: Расстояние между элементами (в длинах волн λ)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.num_elements = num_elements
        self.element_spacing_lambda = element_spacing_lambda

        # Расчет фазовых весов для каждого элемента
        self.phase_weights = [0.0] * num_elements  # В градусах
        self.amplitude_weights = [1.0] * num_elements  # Нормализованные 0.0-1.0

        # Текущий направление луча
        self.current_beam = BeamPattern(
            azimuth_deg=0.0,
            elevation_deg=0.0,
            gain_dbi=Config.GAIN_DBI,
            sidelobe_level_db=Config.SIDELOBE_LEVEL_DB,
        )

        self.logger.info(
            f'BeamForming initialized: {num_elements} elements, '
            f'spacing={element_spacing_lambda}λ'
        )

    def point_beam(self, azimuth_deg: float, elevation_deg: float = 0.0) -> BeamPattern:
        """
        Направить луч в указанном направлении (основной алгоритм MVP).

        Использует фазовую задержку между элементами для создания
        пространственного фильтра в направлении (azimuth, elevation).

        Args:
            azimuth_deg: Целевой азимут в градусах (0-360°)
            elevation_deg: Целевой угол возвышения (-90 до +90°)

        Returns:
            BeamPattern с параметрами диаграммы направленности
        """
        # Валидация входных углов
        azimuth_deg = azimuth_deg % 360.0
        elevation_deg = max(-90.0, min(90.0, elevation_deg))

        try:
            # Расчет фазовых весов для направления луча
            self._calculate_phase_weights(azimuth_deg, elevation_deg)

            # Применение фазовых весов к фазовращателям (для будущих фаз)
            self._apply_phase_weights()

            # Обновление текущего луча
            self.current_beam = BeamPattern(
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                gain_dbi=Config.GAIN_DBI,
                sidelobe_level_db=Config.SIDELOBE_LEVEL_DB,
            )

            self.logger.debug(
                f'Beam pointed to azimuth={azimuth_deg:.1f}°, '
                f'elevation={elevation_deg:.1f}°'
            )
            return self.current_beam

        except Exception as e:
            self.logger.error(f'Beam pointing failed: {e}')
            return self.current_beam

    def scan_beam_pattern(self, step_deg: float = 10.0) -> List[BeamPattern]:
        """
        Сканирование луча по азимуту (поиск оптимального направления).

        Используется при слабом сигнале для поиска максимума усиления.

        Args:
            step_deg: Шаг сканирования в градусах

        Returns:
            Список паттернов для каждого направления
        """
        patterns = []
        for azimuth in range(0, 360, int(step_deg)):
            pattern = self.point_beam(azimuth, elevation_deg=0.0)
            patterns.append(pattern)
            self.logger.debug(f'Scan step: azimuth={azimuth}°, gain={pattern.gain_dbi}dBi')

        self.logger.info(f'Beam scan complete: {len(patterns)} directions')
        return patterns

    def get_current_beam(self) -> BeamPattern:
        """Получить текущий паттерн луча."""
        return self.current_beam

    def get_phase_weights(self) -> List[float]:
        """Получить фазовые веса (в градусах) для каждого элемента."""
        return self.phase_weights.copy()

    def get_amplitude_weights(self) -> List[float]:
        """Получить амплитудные веса (0.0-1.0) для каждого элемента."""
        return self.amplitude_weights.copy()

    # === PRIVATE METHODS ===

    def _calculate_phase_weights(self, azimuth_deg: float, elevation_deg: float) -> None:
        """
        Расчет фазовых весов для направления луча.

        Используется формула фазовой задержки:
            φ_n = (2π / λ) * d_n * sin(θ)
        где:
            d_n = позиция n-го элемента
            θ = целевой угол
            λ = длина волны

        Args:
            azimuth_deg: Азимут в градусах
            elevation_deg: Возвышение в градусах
        """
        wavelength_m = Config.get_wavelength_m()
        element_spacing_m = Config.get_element_spacing_m()

        # Преобразование углов в радианы
        azimuth_rad = math.radians(azimuth_deg)
        elevation_rad = math.radians(elevation_deg)

        # Расчет фазовых весов для линейного массива (упрощение для MVP)
        for i in range(self.num_elements):
            # Позиция элемента относительно первого
            position_m = i * element_spacing_m

            # Фазовая задержка в радианах
            phase_shift_rad = (2 * math.pi / wavelength_m) * position_m * math.sin(azimuth_rad)

            # Преобразование в градусы и нормализация
            phase_deg = math.degrees(phase_shift_rad) % 360.0
            self.phase_weights[i] = phase_deg

        self.logger.debug(f'Phase weights calculated: {[f"{p:.1f}°" for p in self.phase_weights]}')

    def _apply_phase_weights(self) -> None:
        """
        Применение рассчитанных фазовых весов к фазовращателям.

        В MVP это симуляция. В фазе 2 будет реальная отправка по SPI
        к фазовращателям (phase shifters).
        """
        # Для MVP: просто логирование
        self.logger.debug(f'Applying phase weights via SPI (phase 2 feature)')

    def calculate_gain_at_angle(self, azimuth_deg: float, elevation_deg: float = 0.0) -> float:
        """
        Расчет усиления диаграммы направленности в заданном направлении.

        Использует формулу для линейного массива:
            G(θ) = sin²(N*π*d*sin(θ)/λ) / sin²(π*d*sin(θ)/λ)

        Args:
            azimuth_deg: Азимут в градусах
            elevation_deg: Возвышение в градусах

        Returns:
            Усиление в dBi (децибелы относительно изотропного источника)
        """
        try:
            wavelength_m = Config.get_wavelength_m()
            element_spacing_m = Config.get_element_spacing_m()

            azimuth_rad = math.radians(azimuth_deg)

            # Параметр массива
            u = (math.pi * element_spacing_m * math.sin(azimuth_rad)) / wavelength_m

            # Предотвращение деления на ноль
            if abs(u) < 1e-6:
                gain_linear = self.num_elements ** 2
            else:
                numerator = math.sin(self.num_elements * u) ** 2
                denominator = math.sin(u) ** 2
                gain_linear = numerator / denominator

            # Преобразование в dBi (20*log10)
            gain_dbi = 10 * math.log10(max(gain_linear, 1e-6))
            return gain_dbi

        except Exception as e:
            self.logger.error(f'Gain calculation failed: {e}')
            return 0.0

    def __repr__(self) -> str:
        return (
            f'BeamForming(elements={self.num_elements}, '
            f'spacing={self.element_spacing_lambda}λ, '
            f'beam_az={self.current_beam.azimuth_deg:.1f}°, '
            f'beam_el={self.current_beam.elevation_deg:.1f}°)'
        )
