"""
Модуль для управления фазированной антенной решеткой (ФАР) робота.

Поддерживает:
- Инициализацию готовых RF модулей (Qorvo, Wi-Fi 7)
- Управление мощностью TX/RX
- Логирование метрик RSSI и фазы
- Интеграцию с mainloop контроллера робота

Фазы разработки:
1. MVP (неделя 1-3): Готовые модули, базовая инициализация
2. Оптимизация (неделя 4-6): Цифровое управление фазой (встроенное в чип)
3. Расширение (неделя 7-12): Собственная AESA плата, FPGA, цифровое DBF
"""

from .config import Config
from .rf_module import RFModule
from .beamforming import BeamForming
from .power_manager import PowerManager
from .data_logger import DataLogger

__version__ = '1.0.0-alpha'
__all__ = [
    'Config',
    'RFModule',
    'BeamForming',
    'PowerManager',
    'DataLogger',
]
