"""
Логирование метрик ФАР системы для отладки и анализа.

Логирует:
- RSSI (мощность сигнала)
- Фазовые ошибки (для будущих фаз)
- Температуру Power Amplifier
- Потребление энергии
- События инициализации и ошибок
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional

from .config import Config


@dataclass
class LogEntry:
    """Запись в логе метрик RF."""
    timestamp_s: float  # Unix timestamp
    rssi_dbm: float
    phase_error_deg: float
    tx_power_dbm: float
    frequency_hz: float
    pa_temperature_c: float
    thermal_state: str
    event: Optional[str] = None  # 'INIT', 'ERROR', 'SCAN', и т.д.


class DataLogger:
    """
    Логирование метрик ФАР в файл и memory buffer.

    Поддерживает:
    - Ротацию файлов при достижении максимального размера
    - JSON и CSV форматы
    - In-memory кольцевой буфер для последних N записей
    """

    def __init__(self, log_file_path: str = Config.LOG_FILE_PATH, max_file_size_mb: int = 10):
        """
        Инициализация логгера.

        Args:
            log_file_path: Путь к файлу логов
            max_file_size_mb: Максимальный размер файла перед ротацией
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.log_file_path = Path(log_file_path)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        # Ensure parent directory exists
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory circular buffer для последних N записей
        self.buffer_size = 1000
        self.memory_buffer: List[LogEntry] = []

        # Счетчик записей для ротации
        self.entry_count = 0

        self.logger.info(f'DataLogger initialized: {log_file_path}')

    def log_metric(self, entry: LogEntry) -> None:
        """
        Записать метрику в лог.

        Args:
            entry: LogEntry с данными для логирования
        """
        try:
            # Добавить в memory buffer
            self.memory_buffer.append(entry)
            if len(self.memory_buffer) > self.buffer_size:
                self.memory_buffer.pop(0)  # Кольцевой буфер

            # Записать в файл (JSON строка)
            with open(self.log_file_path, 'a') as f:
                entry_dict = asdict(entry)
                f.write(json.dumps(entry_dict) + '\n')

            self.entry_count += 1

            # Ротация если файл слишком большой
            if self.log_file_path.stat().st_size > self.max_file_size_bytes:
                self._rotate_log()

        except Exception as e:
            self.logger.error(f'Failed to log metric: {e}')

    def log_event(self, event_type: str, message: str, rssi_dbm: float = -100.0) -> None:
        """
        Записать событие (инициализация, ошибка, сканирование).

        Args:
            event_type: Тип события ('INIT', 'ERROR', 'SCAN', и т.д.)
            message: Описание события
            rssi_dbm: Текущее значение RSSI (для контекста)
        """
        entry = LogEntry(
            timestamp_s=datetime.now().timestamp(),
            rssi_dbm=rssi_dbm,
            phase_error_deg=0.0,
            tx_power_dbm=Config.TX_POWER_DEFAULT_DBM,
            frequency_hz=Config.FREQUENCY_CENTER_HZ,
            pa_temperature_c=Config.TEMP_AMBIENT_C,
            thermal_state='normal',
            event=f'{event_type}: {message}',
        )
        self.log_metric(entry)
        self.logger.info(f'Event logged: {event_type} - {message}')

    def get_recent_metrics(self, count: int = 100) -> List[LogEntry]:
        """
        Получить последние N записей из memory buffer.

        Args:
            count: Количество записей

        Returns:
            Список LogEntry (новейшие в конце)
        """
        return self.memory_buffer[-count:] if self.memory_buffer else []

    def get_rssi_history(self, count: int = 100) -> List[float]:
        """Получить историю RSSI значений."""
        return [entry.rssi_dbm for entry in self.get_recent_metrics(count)]

    def get_temperature_history(self, count: int = 100) -> List[float]:
        """Получить историю температуры PA."""
        return [entry.pa_temperature_c for entry in self.get_recent_metrics(count)]

    def export_to_csv(self, output_file_path: str) -> None:
        """
        Экспортировать buffer в CSV файл (для анализа в Excel/Python).

        Args:
            output_file_path: Путь к выходному CSV файлу
        """
        try:
            import csv
            with open(output_file_path, 'w', newline='') as f:
                if not self.memory_buffer:
                    self.logger.warning('No data to export')
                    return

                writer = csv.DictWriter(f, fieldnames=asdict(self.memory_buffer[0]).keys())
                writer.writeheader()
                for entry in self.memory_buffer:
                    writer.writerow(asdict(entry))

            self.logger.info(f'Exported {len(self.memory_buffer)} records to {output_file_path}')

        except Exception as e:
            self.logger.error(f'CSV export failed: {e}')

    def clear_memory(self) -> None:
        """Очистить memory buffer."""
        self.memory_buffer.clear()
        self.logger.info('Memory buffer cleared')

    def get_statistics(self) -> dict:
        """
        Получить статистику по logged метрикам.

        Returns:
            dict с статистикой (mean, min, max)
        """
        if not self.memory_buffer:
            return {}

        rssi_values = [e.rssi_dbm for e in self.memory_buffer]
        temp_values = [e.pa_temperature_c for e in self.memory_buffer]
        power_values = [e.tx_power_dbm for e in self.memory_buffer]

        return {
            'total_entries': len(self.memory_buffer),
            'rssi_mean_dbm': sum(rssi_values) / len(rssi_values),
            'rssi_min_dbm': min(rssi_values),
            'rssi_max_dbm': max(rssi_values),
            'temp_mean_c': sum(temp_values) / len(temp_values),
            'temp_max_c': max(temp_values),
            'power_mean_dbm': sum(power_values) / len(power_values),
            'power_max_dbm': max(power_values),
        }

    # === PRIVATE METHODS ===

    def _rotate_log(self) -> None:
        """Ротация логового файла (переименование текущего, создание нового)."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            rotated_path = self.log_file_path.parent / f'{self.log_file_path.stem}_{timestamp}.log'
            self.log_file_path.rename(rotated_path)
            self.logger.info(f'Log rotated to {rotated_path}')

        except Exception as e:
            self.logger.error(f'Log rotation failed: {e}')

    def __repr__(self) -> str:
        return (
            f'DataLogger(file={self.log_file_path}, '
            f'buffer_size={len(self.memory_buffer)}, '
            f'entries={self.entry_count})'
        )
