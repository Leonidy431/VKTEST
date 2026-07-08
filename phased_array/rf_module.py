"""
API для управления RF модулем (Qorvo, Wi-Fi 7).

Handles:
- Инициализация SPI/I2C интерфейсов
- Управление состоянием TX/RX
- Регулирование мощности передатчика
- Мониторинг чувствительности приемника (RSSI)
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from .config import Config


class RFState(Enum):
    """Состояния RF модуля."""
    UNINITIALIZED = 'uninitialized'
    IDLE = 'idle'
    RX_ACTIVE = 'rx_active'
    TX_ACTIVE = 'tx_active'
    ERROR = 'error'


@dataclass
class RFMetrics:
    """Метрики RF сигнала."""
    rssi_dbm: float  # Received Signal Strength Indicator
    snr_db: float  # Signal-to-Noise Ratio
    phase_error_deg: float  # Ошибка фазы (для будущих фаз)
    tx_power_dbm: float  # Текущая мощность TX
    frequency_hz: float  # Текущая рабочая частота


class RFModule:
    """
    Контроллер RF модуля для MVP ФАР системы.

    MVP использует готовый чипсет (Qorvo QPM56xx или Wi-Fi 7),
    управление происходит через SPI/I2C.
    """

    def __init__(self, chip: str = Config.CHIP_MODEL, frequency_hz: float = None):
        """
        Инициализация RF модуля.

        Args:
            chip: Тип чипсета ('Qorvo_QPM5680' или 'WiFi7_MediaTek')
            frequency_hz: Рабочая частота (Hz). Если None, используется центральная
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.chip_model = chip
        self.frequency_hz = frequency_hz or Config.FREQUENCY_CENTER_HZ
        self.state = RFState.UNINITIALIZED
        self.tx_power_dbm = Config.TX_POWER_DEFAULT_DBM
        self.rssi_dbm = -100.0  # Инициальное значение (нет сигнала)
        self.snr_db = 0.0

        # Проверка конфига перед инициализацией
        if not Config.validate():
            self.logger.error('Config validation failed')
            self.state = RFState.ERROR
            raise ValueError('Invalid Config parameters')

        self.logger.info(f'RF Module initialized: chip={chip}, freq={frequency_hz/1e9:.2f} GHz')

    def initialize(self) -> bool:
        """
        Инициализация SPI/I2C интерфейсов и калибровка чипсета.

        Returns:
            True если успешно, False если ошибка
        """
        try:
            self.logger.info(f'Initializing {self.chip_model}...')

            # Симуляция инициализации SPI (в продакшене здесь будет реальный код)
            self._init_spi_interface()

            # Калибровка внутреннего oscillator
            self._calibrate_oscillator()

            # Проверка связи
            if not self._verify_chip_communication():
                raise RuntimeError('Chip communication failed')

            # Установка рабочей частоты
            self._set_frequency(self.frequency_hz)

            # Установка мощности TX по умолчанию
            self._set_tx_power(self.tx_power_dbm)

            self.state = RFState.IDLE
            self.logger.info('RF Module initialization complete')
            return True

        except Exception as e:
            self.logger.error(f'Initialization failed: {e}')
            self.state = RFState.ERROR
            return False

    def enable_rx(self) -> bool:
        """Включить режим приема (RX)."""
        if self.state == RFState.ERROR:
            self.logger.warning('Cannot enable RX: module in ERROR state')
            return False

        try:
            self.logger.debug('Enabling RX mode')
            self.state = RFState.RX_ACTIVE
            return True
        except Exception as e:
            self.logger.error(f'RX enable failed: {e}')
            self.state = RFState.ERROR
            return False

    def enable_tx(self) -> bool:
        """Включить режим передачи (TX)."""
        if self.state == RFState.ERROR:
            self.logger.warning('Cannot enable TX: module in ERROR state')
            return False

        try:
            self.logger.debug(f'Enabling TX mode (power={self.tx_power_dbm} dBm)')
            self.state = RFState.TX_ACTIVE
            return True
        except Exception as e:
            self.logger.error(f'TX enable failed: {e}')
            self.state = RFState.ERROR
            return False

    def disable_tx(self) -> bool:
        """Отключить TX и вернуться в IDLE."""
        try:
            self.state = RFState.IDLE
            self.logger.debug('TX disabled, returning to IDLE')
            return True
        except Exception as e:
            self.logger.error(f'TX disable failed: {e}')
            return False

    def set_tx_power(self, power_dbm: float) -> bool:
        """
        Регулировка мощности передатчика (TX).

        Args:
            power_dbm: Мощность в дБм (децибелы относительно 1 мВт)

        Returns:
            True если успешно, False если значение вне диапазона
        """
        if not (Config.TX_POWER_MIN_DBM <= power_dbm <= Config.TX_POWER_MAX_DBM):
            self.logger.warning(
                f'TX power {power_dbm} dBm outside valid range '
                f'[{Config.TX_POWER_MIN_DBM}, {Config.TX_POWER_MAX_DBM}]'
            )
            return False

        try:
            self._set_tx_power(power_dbm)
            self.tx_power_dbm = power_dbm
            self.logger.info(f'TX power set to {power_dbm} dBm')
            return True
        except Exception as e:
            self.logger.error(f'TX power setting failed: {e}')
            return False

    def get_rssi(self) -> float:
        """
        Получить RSSI (Received Signal Strength Indicator).

        Returns:
            Мощность сигнала в дБм (-100 до 0)
        """
        try:
            # Симуляция чтения RSSI регистра
            self.rssi_dbm = self._read_rssi_register()
            return self.rssi_dbm
        except Exception as e:
            self.logger.error(f'RSSI read failed: {e}')
            return -100.0  # Значение по умолчанию (нет сигнала)

    def get_metrics(self) -> RFMetrics:
        """Получить текущие метрики RF сигнала."""
        return RFMetrics(
            rssi_dbm=self.get_rssi(),
            snr_db=self.snr_db,
            phase_error_deg=0.0,  # Для будущих фаз с фазовращателями
            tx_power_dbm=self.tx_power_dbm,
            frequency_hz=self.frequency_hz,
        )

    def get_state(self) -> RFState:
        """Получить текущее состояние модуля."""
        return self.state

    def get_chip_info(self) -> dict:
        """Информация о чипсете."""
        return {
            'model': self.chip_model,
            'revision': Config.CHIP_REVISION,
            'frequency_hz': self.frequency_hz,
            'tx_power_dbm': self.tx_power_dbm,
            'state': self.state.value,
        }

    # === PRIVATE METHODS (Симуляция для MVP) ===

    def _init_spi_interface(self) -> None:
        """Инициализация SPI шины (симуляция)."""
        self.logger.debug(f'SPI init: clock={Config.SPI_CLOCK_KHZ} kHz, mode={Config.SPI_MODE}')
        # В продакшене: реальная инициализация GPIO + SPI контроллера

    def _calibrate_oscillator(self) -> None:
        """Калибровка внутреннего генератора (симуляция)."""
        self.logger.debug('Oscillator calibration in progress...')

    def _verify_chip_communication(self) -> bool:
        """Проверка связи с чипсетом через SPI (симуляция)."""
        self.logger.debug('Verifying chip communication via SPI...')
        return True  # Для MVP: всегда успех

    def _set_frequency(self, freq_hz: float) -> None:
        """Установка рабочей частоты (симуляция)."""
        if not (Config.FREQUENCY_MIN_HZ <= freq_hz <= Config.FREQUENCY_MAX_HZ):
            raise ValueError(f'Frequency {freq_hz} Hz out of valid range')
        self.logger.debug(f'Setting frequency to {freq_hz/1e9:.3f} GHz')

    def _set_tx_power(self, power_dbm: float) -> None:
        """Установка мощности TX через регистры (симуляция)."""
        self.logger.debug(f'SPI: Setting TX power register to {power_dbm} dBm')

    def _read_rssi_register(self) -> float:
        """Чтение регистра RSSI через SPI (симуляция)."""
        # Симуляция значения RSSI (-85 дБм при нормальной связи)
        return -85.0

    def __repr__(self) -> str:
        return (
            f'RFModule(chip={self.chip_model}, '
            f'freq={self.frequency_hz/1e9:.2f}GHz, '
            f'power={self.tx_power_dbm}dBm, '
            f'state={self.state.value})'
        )
