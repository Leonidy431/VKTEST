"""
Конфигурация RF параметров для MVP ФАР системы.

PEP8 стиль: все параметры как классовые переменные с типами.
"""


class Config:
    """
    Центральная конфигурация для RF модуля и антенной системы.

    Используется при инициализации RFModule и BeamForming.
    Все значения в SI единицах (Герцы, Ватты, метры) кроме особых случаев.
    """

    # === RF Модуль (Qorvo QPM56xx / Wi-Fi 7) ===

    # Идентификатор и тип чипсета
    CHIP_MODEL = 'Qorvo_QPM5680'  # или 'WiFi7_MediaTek'
    CHIP_REVISION = 'A0'

    # Частотный диапазон (рабочая полоса)
    FREQUENCY_MIN_HZ = 5.15e9  # 5.15 ГГц
    FREQUENCY_MAX_HZ = 5.85e9  # 5.85 ГГц
    FREQUENCY_CENTER_HZ = 5.5e9  # 5.5 ГГц (центр диапазона)

    # Мощность передатчика (TX)
    TX_POWER_DEFAULT_DBM = 20  # Номинальная мощность (дБм)
    TX_POWER_MIN_DBM = 14  # Минимум (для энергосбережения)
    TX_POWER_MAX_DBM = 22  # Максимум (ограничение регулятора)
    TX_POWER_STEP_DBM = 1.0  # Шаг регулировки

    # Усилитель мощности (Power Amplifier)
    PA_GAIN_DB = 25  # Усиление PA (типично для 5 ГГц)
    PA_EFFICIENCY_PERCENT = 65  # КПД Power Amplifier
    PA_THERMAL_LIMIT_C = 95  # Максимальная температура (°C)

    # Приемник (RX)
    RX_SENSITIVITY_DBM = -82  # Чувствительность на 10 Мбит/с
    LNA_GAIN_DB = 20  # Усиление Low Noise Amplifier
    LNA_NOISE_FIGURE_DB = 2.5  # Шумовая фигура

    # === Интерфейсы управления ===

    # SPI шина (к фазовращателям, если есть)
    SPI_CLOCK_KHZ = 10000  # 10 МГц
    SPI_MODE = 0  # CPOL=0, CPHA=0

    # I2C шина (к датчикам температуры, питанию)
    I2C_FREQ_HZ = 400000  # 400 кГц
    I2C_SLAVE_ADDR = 0x50  # Адрес слейва (для FPGA контроллера)

    # UART для отладки
    UART_BAUD = 115200
    UART_TIMEOUT_S = 1.0

    # === Антенна (Patch Array) ===

    # Геометрия массива
    NUM_ELEMENTS = 4  # Количество элементов (2×2 для MVP)
    ELEMENT_SPACING_LAMBDA = 0.5  # Расстояние между элементами (в волнах)

    # Диаграмма направленности
    BEAMWIDTH_DEG = 60  # 3dB beamwidth (примерно)
    SIDELOBE_LEVEL_DB = -15  # Уровень боковых лепестков
    GAIN_DBI = 8  # Усиление антенны относительно изотропного (dBi)

    # Поляризация
    POLARIZATION = 'LINEAR_H'  # Linear Horizontal

    # === Управление питанием ===

    # Напряжение питания
    VBAT_NOMINAL_V = 48  # Основное напряжение батареи (V)
    V_RF_CORE_V = 3.3  # Напряжение ядра RF (V)
    V_ANALOG_V = 5.0  # Аналоговое напряжение (V)

    # Пороги энергосбережения
    POWER_TX_IDLE_MW = 100  # Потребление в режиме ожидания (мВт)
    POWER_TX_ACTIVE_MW = 500  # Потребление при TX (мВт)
    POWER_RX_ACTIVE_MW = 200  # Потребление при RX (мВт)

    # === Тепловой менеджмент ===

    TEMP_AMBIENT_C = 25  # Номинальная температура окружающей среды
    TEMP_RISE_LIMIT_C = 15  # Максимально допустимое повышение T
    THERMAL_TIME_CONSTANT_S = 60  # Постоянная времени нагрева
    HEATSINK_MATERIAL = 'Aluminum'  # Радиатор
    HEATSINK_AREA_MM2 = 100  # Площадь теплоотвода

    # === Логирование и отладка ===

    # Логирование метрик
    LOG_RSSI_ENABLED = True
    LOG_PHASE_ERROR_ENABLED = True
    LOG_TEMP_ENABLED = True
    LOG_INTERVAL_S = 0.5  # Интервал между записями (500 мс)

    # Уровень детализации
    DEBUG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE_PATH = '/tmp/vktest_rf.log'

    # === Специфика робота ===

    # Размеры и расположение на корпусе
    ANTENNA_MOUNTING_HEIGHT_MM = 150  # Высота над землей
    ANTENNA_OFFSET_FROM_CENTER_MM = 50  # Смещение от оси робота

    # Максимальная дальность связи (для диаграмм и планирования)
    LINK_RANGE_NOMINAL_M = 80  # Номинальная дальность в открытом пространстве
    LINK_RANGE_INDOOR_M = 30  # В помещении с отражениями

    # === Версионирование конфига ===

    CONFIG_VERSION = '1.0'
    CONFIG_LAST_UPDATED = '2026-07-08'

    @classmethod
    def get_wavelength_m(cls) -> float:
        """Длина волны в метрах на центральной частоте."""
        c = 3e8  # скорость света
        return c / cls.FREQUENCY_CENTER_HZ

    @classmethod
    def get_element_spacing_m(cls) -> float:
        """Расстояние между элементами в метрах."""
        return cls.ELEMENT_SPACING_LAMBDA * cls.get_wavelength_m()

    @classmethod
    def validate(cls) -> bool:
        """
        Проверка консистентности конфига.

        Returns:
            True если валиден, False если есть несоответствия
        """
        # Проверка частотного диапазона
        if not (cls.FREQUENCY_MIN_HZ < cls.FREQUENCY_CENTER_HZ < cls.FREQUENCY_MAX_HZ):
            return False

        # Проверка мощности
        if not (cls.TX_POWER_MIN_DBM <= cls.TX_POWER_DEFAULT_DBM <= cls.TX_POWER_MAX_DBM):
            return False

        # Проверка пороговых значений
        if cls.TEMP_RISE_LIMIT_C < 5 or cls.TEMP_RISE_LIMIT_C > 50:
            return False

        # Проверка антенны
        if cls.NUM_ELEMENTS < 1:
            return False

        return True
