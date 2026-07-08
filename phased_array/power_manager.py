"""
Управление энергопотреблением и тепловым режимом ФАР модуля.

Features:
- Адаптивное управление мощностью TX в зависимости от расстояния
- Контроль температуры PA (Power Amplifier)
- Энергосбережение в режиме RX
- Тепловая защита с дросселированием мощности
"""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from .config import Config
from .rf_module import RFModule


class ThermalState(Enum):
    """Состояния теплового режима."""
    COOL = 'cool'  # <T_rise/3
    NORMAL = 'normal'  # T_rise/3 до 2*T_rise/3
    WARM = 'warm'  # 2*T_rise/3 до T_rise
    HOT = 'hot'  # >T_rise, нужно дросселирование


@dataclass
class PowerMetrics:
    """Метрики энергопотребления."""
    tx_power_dbm: float
    tx_current_ma: float  # Ток TX в миллиамперах
    rx_current_ma: float  # Ток RX
    total_current_ma: float  # Общий ток
    pa_temperature_c: float  # Температура Power Amplifier
    thermal_state: ThermalState
    battery_voltage_v: float


class PowerManager:
    """
    Оптимизация энергопотребления ФАР.

    MVP стратегия:
    - TX мощность регулируется в зависимости от RSSI
    - Если сигнал слабый, повысить мощность TX
    - Если тепловой предел достигнут, снизить мощность
    """

    def __init__(self, rf_module: Optional[RFModule] = None):
        """
        Инициализация Power Manager.

        Args:
            rf_module: Ссылка на RFModule для регулировки мощности
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rf_module = rf_module
        self.pa_temperature_c = Config.TEMP_AMBIENT_C
        self.battery_voltage_v = Config.VBAT_NOMINAL_V
        self.thermal_state = ThermalState.COOL

        # История для фильтрации шума
        self.rssi_history = []
        self.max_history_size = 10

        self.logger.info('PowerManager initialized')

    def optimize_tx_power(self, rssi_dbm: float, target_rssi_dbm: float = -75.0) -> float:
        """
        Адаптивное управление мощностью TX.

        Алгоритм:
        - Если RSSI < целевого, повысить TX мощность
        - Если RSSI > целевого, снизить TX мощность (энергосбережение)
        - Учитывать тепловое состояние

        Args:
            rssi_dbm: Текущий RSSI (дБм)
            target_rssi_dbm: Целевой RSSI (дБм, типично -75)

        Returns:
            Рекомендуемая мощность TX (дБм)
        """
        # Добавить в историю для фильтрации шума
        self.rssi_history.append(rssi_dbm)
        if len(self.rssi_history) > self.max_history_size:
            self.rssi_history.pop(0)

        # Средний RSSI (фильтр)
        avg_rssi = sum(self.rssi_history) / len(self.rssi_history)
        rssi_error = target_rssi_dbm - avg_rssi  # Ошибка управления

        # Получить текущую мощность
        if self.rf_module:
            current_power = self.rf_module.tx_power_dbm
        else:
            current_power = Config.TX_POWER_DEFAULT_DBM

        # P-регулятор (пропорциональный контроллер)
        kp = 1.0  # Коэффициент пропорциональности
        power_adjustment = kp * rssi_error

        # Расчет новой мощности
        new_power = current_power + power_adjustment

        # Ограничение пределами
        new_power = max(
            Config.TX_POWER_MIN_DBM,
            min(Config.TX_POWER_MAX_DBM, new_power)
        )

        # Учет теплового состояния
        if self.thermal_state == ThermalState.HOT:
            # Аварийное дросселирование
            new_power = min(new_power, Config.TX_POWER_DEFAULT_DBM - 4)
            self.logger.warning('Thermal throttling activated!')

        self.logger.debug(
            f'TX power optimization: RSSI={rssi_dbm:.1f} dBm, '
            f'target={target_rssi_dbm:.1f}, adjustment={power_adjustment:.1f} dBm'
        )

        return new_power

    def apply_tx_power(self, power_dbm: float) -> bool:
        """
        Применить рассчитанную мощность TX к RF модулю.

        Args:
            power_dbm: Мощность в дБм

        Returns:
            True если успешно
        """
        if not self.rf_module:
            self.logger.warning('RF Module not attached, cannot apply power')
            return False

        return self.rf_module.set_tx_power(power_dbm)

    def estimate_pa_temperature(self, tx_power_dbm: float, ambient_temp_c: float,
                                 time_elapsed_s: float) -> float:
        """
        Оценка температуры Power Amplifier.

        Модель: T(t) = T_amb + ΔT_max * (1 - exp(-t/τ))
        где:
            ΔT_max = (P_tx * (1 - η)) / (G_th)
            τ = постоянная времени нагрева
            η = КПД Power Amplifier

        Args:
            tx_power_dbm: Мощность TX в дБм
            ambient_temp_c: Температура окружающей среды (°C)
            time_elapsed_s: Время работы в режиме TX (секунды)

        Returns:
            Оценная температура PA (°C)
        """
        # Преобразование из дБм в Ватты
        # P (W) = 10^(P(dBm)/10) / 1000
        tx_power_w = 10.0 ** (tx_power_dbm / 10.0) / 1000.0

        # Тепловыделение (потери)
        heat_dissipation_w = tx_power_w * (1 - Config.PA_EFFICIENCY_PERCENT / 100.0)

        # Максимальное повышение температуры (установившееся значение)
        thermal_resistance = Config.TEMP_RISE_LIMIT_C / (heat_dissipation_w + 0.1)
        delta_t_max = Config.TEMP_RISE_LIMIT_C * (heat_dissipation_w / 0.5)

        # Экспоненциальное приближение к установившейся температуре
        tau = Config.THERMAL_TIME_CONSTANT_S
        delta_t = delta_t_max * (1 - math.exp(-time_elapsed_s / tau))

        # Общая температура
        pa_temp = ambient_temp_c + delta_t

        return pa_temp

    def update_thermal_state(self, pa_temperature_c: float) -> ThermalState:
        """
        Обновить тепловое состояние на основе температуры PA.

        Args:
            pa_temperature_c: Температура Power Amplifier (°C)

        Returns:
            Новое тепловое состояние
        """
        t_limit = Config.TEMP_AMBIENT_C + Config.TEMP_RISE_LIMIT_C
        t_quarter = Config.TEMP_RISE_LIMIT_C / 3

        if pa_temperature_c < Config.TEMP_AMBIENT_C + t_quarter:
            self.thermal_state = ThermalState.COOL
        elif pa_temperature_c < Config.TEMP_AMBIENT_C + 2 * t_quarter:
            self.thermal_state = ThermalState.NORMAL
        elif pa_temperature_c < t_limit:
            self.thermal_state = ThermalState.WARM
        else:
            self.thermal_state = ThermalState.HOT
            self.logger.warning(f'PA over-temperature alert: {pa_temperature_c:.1f}°C')

        return self.thermal_state

    def get_tx_current_ma(self, tx_power_dbm: float) -> float:
        """
        Оценка тока TX (в миллиамперах) на основе мощности.

        Приблизительно: I (mA) ≈ P (mW) / V (V) / η
        """
        power_mw = 10.0 ** (tx_power_dbm / 10.0)
        current_ma = power_mw / Config.V_RF_CORE_V / (Config.PA_EFFICIENCY_PERCENT / 100.0)
        return current_ma

    def get_rx_current_ma(self) -> float:
        """Приблизительный ток RX (примерно 30-50% от TX на max мощности)."""
        return Config.POWER_RX_ACTIVE_MW / Config.V_RF_CORE_V

    def get_power_metrics(self, tx_power_dbm: float, pa_temp_c: float) -> PowerMetrics:
        """Получить полные метрики энергопотребления."""
        tx_current = self.get_tx_current_ma(tx_power_dbm)
        rx_current = self.get_rx_current_ma()

        return PowerMetrics(
            tx_power_dbm=tx_power_dbm,
            tx_current_ma=tx_current,
            rx_current_ma=rx_current,
            total_current_ma=tx_current + rx_current,
            pa_temperature_c=pa_temp_c,
            thermal_state=self.thermal_state,
            battery_voltage_v=self.battery_voltage_v,
        )

    def __repr__(self) -> str:
        return (
            f'PowerManager(thermal_state={self.thermal_state.value}, '
            f'pa_temp={self.pa_temperature_c:.1f}°C)'
        )


import math
