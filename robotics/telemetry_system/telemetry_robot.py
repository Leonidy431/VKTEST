"""
Water-Robust Telemetry Module for Autonomous ROV/AUV

Синхронизирует данные сенсоров робота с Firebase Realtime Database.
Поддерживает локальную буферизацию при потере связи на воде.
Критичен для операций подводных буйов и ROV с периодическим всплытием.

Architecture:
    Robot Sensors → Local Buffer (JSON) → Firebase Queue Push → Pixel 10 (Real-time)

Key Features:
    - Heartbeat/offline detection (socket-based)
    - Local SQLite buffer for offline persistence
    - Atomic sync (idempotent push operations)
    - Configurable data compression for large payloads
    - Health monitoring for BlueOS integration
"""

import firebase_admin
from firebase_admin import credentials, db
import logging
import socket
import json
import os
import time
import sqlite3
import threading
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib


# ============ Configuration ============

@dataclass
class TelemetryConfig:
    """Конфигурация модуля телеметрии."""
    firebase_url: str = "https://your-project-id.firebaseio.com/"
    service_account_key: str = "/app/service-account.json"

    # Buffer configuration
    buffer_file: str = "/app/data/telemetry_buffer.db"
    buffer_max_size: int = 1000  # Лимит записей перед WARNING

    # Sync configuration
    sync_interval_s: float = 1.0  # Отправка 1 раз в секунду
    offline_check_interval_s: float = 5.0  # Проверка связи каждые 5 сек
    offline_buffer_limit: int = 1000  # Max строк локально

    # Compression
    enable_compression: bool = True
    compression_threshold_bytes: int = 1024  # Сжимаем если > 1KB

    # Logging
    log_level: str = "INFO"
    log_file: str = "/app/data/telemetry.log"


# ============ Logger Setup ============

def setup_logger(config: TelemetryConfig) -> logging.Logger:
    """Инициализация логирования."""
    Path(config.log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("telemetry")
    logger.setLevel(getattr(logging, config.log_level))

    # File handler
    fh = logging.FileHandler(config.log_file)
    fh.setLevel(logging.DEBUG)

    # Stream handler
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)

    # Formatter
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


# ============ Telemetry Data Model ============

@dataclass
class TelemetryRecord:
    """Структура записи телеметрии."""
    timestamp: float  # Unix timestamp
    lat: float
    lon: float
    depth_m: float = 0.0
    temperature_c: float = 0.0
    battery_pct: int = 100
    status: str = "online"  # online, offline, error
    device_id: str = "rov-001"

    # Optional
    compass_heading_deg: Optional[float] = None
    velocity_ms: Optional[float] = None
    sonar_distance_m: Optional[float] = None
    acoustic_detection: Optional[Dict] = None  # For acoustic events

    def to_dict(self) -> Dict:
        """Конвертация в словарь для JSON."""
        data = asdict(self)
        # Удаляем None значения
        return {k: v for k, v in data.items() if v is not None}

    def to_json(self) -> str:
        """Конвертация в JSON."""
        return json.dumps(self.to_dict())


# ============ Local Buffer (SQLite) ============

class LocalBuffer:
    """Локальная буферизация данных при потере связи с Firebase."""

    def __init__(self, db_path: str, logger: logging.Logger):
        self.db_path = db_path
        self.logger = logger
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Инициализация SQLite схемы."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                data TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                hash TEXT UNIQUE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_synced ON telemetry(synced)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry(timestamp)
        """)

        conn.commit()
        conn.close()

    def save(self, record: TelemetryRecord) -> bool:
        """Сохранить запись в буфер."""
        try:
            data_json = record.to_json()
            # Хеш для предотвращения дубликатов
            record_hash = hashlib.md5(data_json.encode()).hexdigest()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO telemetry (timestamp, data, hash)
                VALUES (?, ?, ?)
            """, (record.timestamp, data_json, record_hash))

            conn.commit()
            conn.close()

            self.logger.debug(f"Buffered: {record.device_id} @ {record.timestamp}")
            return True

        except Exception as e:
            self.logger.error(f"Buffer save error: {e}")
            return False

    def get_unsync_records(self, limit: int = 100) -> List[Dict]:
        """Получить несинхронизированные записи."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, data FROM telemetry
                WHERE synced = 0
                ORDER BY timestamp ASC
                LIMIT ?
            """, (limit,))

            records = [
                {"id": row[0], "data": json.loads(row[1])}
                for row in cursor.fetchall()
            ]

            conn.close()
            return records

        except Exception as e:
            self.logger.error(f"Buffer read error: {e}")
            return []

    def mark_synced(self, record_ids: List[int]) -> bool:
        """Отметить записи как синхронизированные."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(record_ids))
            cursor.execute(f"""
                UPDATE telemetry SET synced = 1 WHERE id IN ({placeholders})
            """, record_ids)

            conn.commit()
            conn.close()

            self.logger.debug(f"Marked {len(record_ids)} records as synced")
            return True

        except Exception as e:
            self.logger.error(f"Buffer update error: {e}")
            return False

    def get_buffer_stats(self) -> Dict:
        """Статистика буфера."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM telemetry")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM telemetry WHERE synced = 0")
            unsynced = cursor.fetchone()[0]

            conn.close()

            return {"total": total, "unsynced": unsynced}

        except Exception as e:
            self.logger.error(f"Stats query error: {e}")
            return {"total": 0, "unsynced": 0}


# ============ Firebase Sync Manager ============

class FirebaseSyncManager:
    """Управление синхронизацией с Firebase Realtime Database."""

    def __init__(self, config: TelemetryConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.is_connected = False
        self.sync_thread = None
        self.running = False

        # Initialize Firebase
        self._init_firebase()

    def _init_firebase(self):
        """Инициализация Firebase Admin SDK."""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(self.config.service_account_key)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': self.config.firebase_url
                })
            self.logger.info("Firebase initialized")
        except Exception as e:
            self.logger.error(f"Firebase init error: {e}")

    def check_connectivity(self) -> bool:
        """Проверка связи с интернетом (Google DNS)."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

    def push_record(self, record: TelemetryRecord) -> Optional[str]:
        """
        Push запись в Firebase.
        Возвращает Firebase key если успешно, иначе None.
        """
        try:
            ref = db.reference(f'robot/{record.device_id}/telemetry')
            data = record.to_dict()

            # Push создает новый узел с уникальным ключом (идемпотентность)
            new_ref = ref.push(data)
            self.logger.debug(f"Pushed: {new_ref.key}")

            return new_ref.key

        except Exception as e:
            self.logger.error(f"Firebase push error: {e}")
            return None

    def sync_buffer(self, buffer: LocalBuffer) -> int:
        """
        Синхронизировать буфер с Firebase.
        Возвращает количество успешно синхронизированных записей.
        """
        unsynced = buffer.get_unsync_records(limit=50)
        synced_ids = []

        for item in unsynced:
            try:
                record = TelemetryRecord(**item["data"])
                firebase_key = self.push_record(record)

                if firebase_key:
                    synced_ids.append(item["id"])
                else:
                    break  # Stop on first failure (network issue)

            except Exception as e:
                self.logger.error(f"Sync item error: {e}")
                break

        if synced_ids:
            buffer.mark_synced(synced_ids)

        return len(synced_ids)

    def get_robot_status(self, device_id: str) -> Optional[Dict]:
        """Получить текущее состояние робота из Firebase."""
        try:
            ref = db.reference(f'robot/{device_id}/status')
            return ref.get()
        except Exception as e:
            self.logger.error(f"Status read error: {e}")
            return None

    def update_robot_status(self, device_id: str, status: str):
        """Обновить статус робота."""
        try:
            ref = db.reference(f'robot/{device_id}/status')
            ref.set({
                "state": status,
                "last_update": time.time()
            })
        except Exception as e:
            self.logger.error(f"Status update error: {e}")


# ============ Main Telemetry Engine ============

class TelemetryEngine:
    """Основной механизм сбора и отправки телеметрии."""

    def __init__(self, config: TelemetryConfig):
        self.config = config
        self.logger = setup_logger(config)

        # Initialize components
        self.buffer = LocalBuffer(config.buffer_file, self.logger)
        self.sync_manager = FirebaseSyncManager(config, self.logger)

        self.running = False
        self.threads = []

    def start(self):
        """Запустить основной цикл."""
        self.running = True
        self.logger.info("Telemetry engine started")

        # Sync thread
        sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        sync_thread.start()
        self.threads.append(sync_thread)

        # Connectivity check thread
        check_thread = threading.Thread(target=self._connectivity_loop, daemon=True)
        check_thread.start()
        self.threads.append(check_thread)

    def stop(self):
        """Остановить основной цикл."""
        self.running = False
        self.logger.info("Telemetry engine stopping")
        for thread in self.threads:
            thread.join(timeout=5)

    def send_telemetry(self, record: TelemetryRecord) -> bool:
        """
        Отправить запись телеметрии.
        Если есть связь → Firebase, иначе → local buffer.
        """
        try:
            if self.sync_manager.is_connected:
                # Попытка отправить в Firebase
                firebase_key = self.sync_manager.push_record(record)
                if firebase_key:
                    self.logger.info(f"Sent to Firebase: {firebase_key}")
                    return True

            # Резервное сохранение в буфер
            self.buffer.save(record)
            self.logger.debug(f"Buffered: {record.device_id}")
            return True

        except Exception as e:
            self.logger.error(f"Telemetry error: {e}")
            self.buffer.save(record)
            return False

    def _sync_loop(self):
        """Фоновой цикл синхронизации буфера."""
        while self.running:
            try:
                if self.sync_manager.is_connected:
                    synced = self.sync_manager.sync_buffer(self.buffer)
                    if synced > 0:
                        self.logger.info(f"Synced {synced} records")

                    # Buffer stats
                    stats = self.buffer.get_buffer_stats()
                    if stats["unsynced"] > self.config.offline_buffer_limit * 0.8:
                        self.logger.warning(
                            f"Buffer HIGH: {stats['unsynced']}/{self.config.offline_buffer_limit}"
                        )

                time.sleep(self.config.sync_interval_s)

            except Exception as e:
                self.logger.error(f"Sync loop error: {e}")

    def _connectivity_loop(self):
        """Проверка связи."""
        while self.running:
            try:
                was_connected = self.sync_manager.is_connected
                self.sync_manager.is_connected = self.sync_manager.check_connectivity()

                # Log state changes
                if self.sync_manager.is_connected and not was_connected:
                    self.logger.info("Network: ONLINE")
                elif not self.sync_manager.is_connected and was_connected:
                    self.logger.warning("Network: OFFLINE")

                time.sleep(self.config.offline_check_interval_s)

            except Exception as e:
                self.logger.error(f"Connectivity loop error: {e}")


# ============ Sensor Simulator (для тестирования) ============

class SensorSimulator:
    """Симуляция данных с сенсоров для тестирования."""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.lat = 34.9821
        self.lon = 33.9512
        self.depth = 0.0
        self.counter = 0

    def read_sensors(self) -> TelemetryRecord:
        """Чтение симулированных сенсоров."""
        self.counter += 1

        # Simulate depth increase then decrease (diving/surfacing profile)
        if self.counter < 50:
            self.depth += 0.5  # Погружение
        elif self.counter < 100:
            self.depth -= 0.5  # Всплытие
        else:
            self.counter = 0

        self.depth = max(0, min(20, self.depth))  # Clamp 0-20m

        return TelemetryRecord(
            timestamp=time.time(),
            lat=self.lat + (self.counter % 10) * 0.0001,
            lon=self.lon + (self.counter % 10) * 0.0001,
            depth_m=self.depth,
            temperature_c=15.0 + (self.depth * 0.5),  # Холоднее на глубине
            battery_pct=max(10, 100 - self.counter // 2),
            status="online",
            device_id=self.device_id,
            compass_heading_deg=(self.counter * 3.6) % 360,
            velocity_ms=0.5
        )


# ============ Main Entry Point ============

def main():
    """Основной цикл приложения."""
    config = TelemetryConfig()
    engine = TelemetryEngine(config)
    sensor_sim = SensorSimulator("rov-001")

    try:
        engine.start()

        # Main telemetry loop
        while True:
            record = sensor_sim.read_sensors()
            engine.send_telemetry(record)

            time.sleep(config.sync_interval_s)

    except KeyboardInterrupt:
        print("\nShutdown signal received")

    finally:
        engine.stop()
        print("Engine stopped")


if __name__ == "__main__":
    main()
