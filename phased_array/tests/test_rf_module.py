"""
Tests для RF модуля (Qorvo, Wi-Fi 7).

Проверяет:
- Инициализацию
- Управление TX/RX
- Регулировку мощности
- Чтение RSSI
"""

import pytest
import logging

from phased_array.config import Config
from phased_array.rf_module import RFModule, RFState, RFMetrics


class TestRFModuleInit:
    """Тесты инициализации RF модуля."""

    def test_module_creation(self):
        """Создание экземпляра RFModule."""
        rf = RFModule()
        assert rf.chip_model == Config.CHIP_MODEL
        assert rf.state == RFState.UNINITIALIZED

    def test_config_validation(self):
        """Проверка валидности конфига."""
        assert Config.validate() is True

    def test_initialization(self):
        """Инициализация RF модуля."""
        rf = RFModule()
        result = rf.initialize()
        assert result is True
        assert rf.state == RFState.IDLE

    def test_initialization_invalid_config(self):
        """Инициализация при невалидном конфиге (симуляция)."""
        # Сохранить оригинальные значения
        orig_freq = Config.FREQUENCY_CENTER_HZ
        orig_min = Config.FREQUENCY_MIN_HZ
        try:
            # Поломать конфиг (центральная частота ниже минимума)
            Config.FREQUENCY_MIN_HZ = 5.5e9
            Config.FREQUENCY_CENTER_HZ = 4.0e9  # Вне диапазона
            # Config.validate() вернет False, и RFModule.__init__ выбросит исключение
            with pytest.raises(ValueError):
                rf = RFModule()
        finally:
            # Восстановить конфиг
            Config.FREQUENCY_CENTER_HZ = orig_freq
            Config.FREQUENCY_MIN_HZ = orig_min


class TestRFModuleRX:
    """Тесты режима приема (RX)."""

    def test_enable_rx(self):
        """Включение режима приема."""
        rf = RFModule()
        rf.initialize()
        result = rf.enable_rx()
        assert result is True
        assert rf.state == RFState.RX_ACTIVE

    def test_enable_rx_from_error_state(self):
        """Попытка включить RX из состояния ERROR."""
        rf = RFModule()
        rf.state = RFState.ERROR
        result = rf.enable_rx()
        assert result is False


class TestRFModuleTX:
    """Тесты режима передачи (TX)."""

    def test_enable_tx(self):
        """Включение режима передачи."""
        rf = RFModule()
        rf.initialize()
        result = rf.enable_tx()
        assert result is True
        assert rf.state == RFState.TX_ACTIVE

    def test_disable_tx(self):
        """Отключение TX."""
        rf = RFModule()
        rf.initialize()
        rf.enable_tx()
        result = rf.disable_tx()
        assert result is True
        assert rf.state == RFState.IDLE

    def test_set_tx_power_valid(self):
        """Установка мощности TX (валидное значение)."""
        rf = RFModule()
        rf.initialize()
        result = rf.set_tx_power(20.0)
        assert result is True
        assert rf.tx_power_dbm == 20.0

    def test_set_tx_power_min(self):
        """Установка мощности TX на минимум."""
        rf = RFModule()
        rf.initialize()
        result = rf.set_tx_power(Config.TX_POWER_MIN_DBM)
        assert result is True

    def test_set_tx_power_max(self):
        """Установка мощности TX на максимум."""
        rf = RFModule()
        rf.initialize()
        result = rf.set_tx_power(Config.TX_POWER_MAX_DBM)
        assert result is True

    def test_set_tx_power_out_of_range_low(self):
        """Установка мощности TX ниже минимума."""
        rf = RFModule()
        rf.initialize()
        result = rf.set_tx_power(Config.TX_POWER_MIN_DBM - 5.0)
        assert result is False
        # TX мощность не должна была измениться
        assert rf.tx_power_dbm == Config.TX_POWER_DEFAULT_DBM

    def test_set_tx_power_out_of_range_high(self):
        """Установка мощности TX выше максимума."""
        rf = RFModule()
        rf.initialize()
        result = rf.set_tx_power(Config.TX_POWER_MAX_DBM + 5.0)
        assert result is False


class TestRFModuleMetrics:
    """Тесты получения метрик."""

    def test_get_rssi(self):
        """Чтение RSSI."""
        rf = RFModule()
        rf.initialize()
        rssi = rf.get_rssi()
        # MVP симуляция возвращает -85 дБм
        assert -100 <= rssi <= 0

    def test_get_metrics(self):
        """Получение всех метрик."""
        rf = RFModule()
        rf.initialize()
        metrics = rf.get_metrics()
        assert isinstance(metrics, RFMetrics)
        assert metrics.frequency_hz == Config.FREQUENCY_CENTER_HZ
        assert Config.TX_POWER_MIN_DBM <= metrics.tx_power_dbm <= Config.TX_POWER_MAX_DBM

    def test_get_chip_info(self):
        """Получение информации о чипсете."""
        rf = RFModule()
        rf.initialize()
        info = rf.get_chip_info()
        assert info['model'] == Config.CHIP_MODEL
        assert info['frequency_hz'] == Config.FREQUENCY_CENTER_HZ
        assert info['state'] == RFState.IDLE.value


class TestRFModuleStateTransitions:
    """Тесты переходов между состояниями."""

    def test_idle_to_rx(self):
        """Переход IDLE → RX."""
        rf = RFModule()
        rf.initialize()
        assert rf.state == RFState.IDLE
        rf.enable_rx()
        assert rf.state == RFState.RX_ACTIVE

    def test_idle_to_tx(self):
        """Переход IDLE → TX."""
        rf = RFModule()
        rf.initialize()
        assert rf.state == RFState.IDLE
        rf.enable_tx()
        assert rf.state == RFState.TX_ACTIVE

    def test_tx_to_idle(self):
        """Переход TX → IDLE."""
        rf = RFModule()
        rf.initialize()
        rf.enable_tx()
        rf.disable_tx()
        assert rf.state == RFState.IDLE

    def test_rx_to_tx(self):
        """Переход RX → TX (должен быть через IDLE)."""
        rf = RFModule()
        rf.initialize()
        rf.enable_rx()
        assert rf.state == RFState.RX_ACTIVE
        # Прямой переход TX может быть, но безопаснее через IDLE
        rf.disable_tx()  # Гарантированно вернёт в IDLE
        rf.enable_tx()
        assert rf.state == RFState.TX_ACTIVE


class TestRFModuleRepr:
    """Тест строкового представления."""

    def test_repr(self):
        """Проверка __repr__."""
        rf = RFModule()
        rf.initialize()
        repr_str = repr(rf)
        assert 'RFModule' in repr_str
        assert 'idle' in repr_str.lower()  # state='idle' (lowercase)
        assert 'GHz' in repr_str
