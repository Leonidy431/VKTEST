"""
MQTT-Based Resilient Sync Module with QoS 2 (Exactly Once)

Адресует критические слепые пятна:
1. "Firebase Lag" → MQTT QoS 2 (гарантированная доставка)
2. "Offline Identity" → Автономный режим с локальной очередью
3. Network failures → Graceful degradation, не спам ошибок

Архитектура:
    Robot Data → Local SQLite → MQTT Broker → Firebase (async)
                                      ↓
                                Pixel 10 (real-time)
"""

import paho.mqtt.client as mqtt
import socket
import logging
import json
import sqlite3
import time
import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib


@dataclass
class MQTTConfig:
    """Конфигурация MQTT брокера."""
    broker_host: str = "mqtt.example.com"  # Или локальный mosquitto
    broker_port: int = 8883  # TLS
    client_id: str = "rov-telemetry-001"

    # Authentication
    username: str = "robot_user"
    password: str = "secure_password"
    ca_cert: str = "/app/certs/ca.crt"
    client_cert: str = "/app/certs/client.crt"
    client_key: str = "/app/certs/client.key"

    # Topics
    telemetry_topic: str = "robot/telemetry"
    status_topic: str = "robot/status"
    command_topic: str = "robot/commands"

    # QoS
    qos_level: int = 2  # Exactly Once

    # Timeouts
    keep_alive: int = 60
    connection_timeout: int = 10
    message_timeout: int = 30


class ResilienceMonitor:
    """Мониторинг и логирование состояния связи (исключение socket.gaierror)."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.connection_state = "INIT"
        self.last_disconnect_reason = None
        self.disconnect_count = 0
        self.last_successful_publish = 0

    def check_connectivity(
        self,
        host: str = "8.8.8.8",
        port: int = 53,
        timeout: int = 3
    ) -> bool:
        """
        Проверка связи с учетом различных типов ошибок.
        Обрабатывает:
        - socket.gaierror (DNS resolution failure)
        - socket.timeout (network timeout)
        - OSError (general network error)
        """
        socket.setdefaulttimeout(timeout)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            sock.close()

            if self.connection_state != "ONLINE":
                self.logger.info("Network: ONLINE (recovered)")
                self.connection_state = "ONLINE"

            return True

        except socket.gaierror as e:
            # DNS resolution failed (typical on satellite networks)
            self.logger.warning(f"DNS resolution failed: {e}")
            self.last_disconnect_reason = "DNS_FAILURE"
            return False

        except socket.timeout:
            self.logger.warning("Network timeout (signal degraded)")
            self.last_disconnect_reason = "TIMEOUT"
            return False

        except OSError as e:
            self.logger.error(f"Network error: {e}")
            self.last_disconnect_reason = "OS_ERROR"
            return False

        except Exception as e:
            self.logger.error(f"Unexpected error in connectivity check: {e}")
            self.last_disconnect_reason = "UNKNOWN"
            return False

        finally:
            self.connection_state = "OFFLINE"
            self.disconnect_count += 1


class MQTTResiliencyManager:
    """
    MQTT-based telemetry с локальной SQL очередью (QoS 2 + retry).
    Заменяет Firebase на MQTT для гарантированной доставки на воде.
    """

    def __init__(self, config: MQTTConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.monitor = ResilienceMonitor(logger)

        # MQTT client
        self.client = mqtt.Client(
            client_id=config.client_id,
            protocol=mqtt.MQTTv311,
            clean_session=False  # Persistent session
        )

        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_message = self._on_message

        self.is_connected = False
        self.publish_queue = []
        self.pending_acks = {}  # Track QoS 2 delivery

    def _on_connect(self, client, userdata, flags, rc):
        """Callback для подключения."""
        if rc == 0:
            self.logger.info("MQTT connected")
            self.is_connected = True
            self.monitor.connection_state = "CONNECTED"

            # Subscribe to command topic
            client.subscribe(self.config.command_topic, qos=self.config.qos_level)

            # Resend pending messages
            self._flush_queue()

        else:
            error_codes = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized"
            }
            self.logger.error(f"MQTT connect failed: {error_codes.get(rc, 'Unknown')}")
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        """Callback для разорыва соединения."""
        if rc != 0:
            self.logger.warning(f"Unexpected MQTT disconnect: {rc}")
            self.is_connected = False
            self.monitor.connection_state = "OFFLINE"

    def _on_publish(self, client, userdata, mid):
        """Callback для подтверждения публикации (QoS 2)."""
        if mid in self.pending_acks:
            del self.pending_acks[mid]
            self.monitor.last_successful_publish = time.time()
            self.logger.debug(f"Message {mid} delivered (QoS 2)")

    def _on_message(self, client, userdata, msg):
        """Callback для входящих команд."""
        try:
            payload = json.loads(msg.payload.decode())
            self.logger.info(f"Command received: {payload}")
            # Обработка команд (например, изменение режима работы)
        except Exception as e:
            self.logger.error(f"Message parsing error: {e}")

    def connect_to_broker(self) -> bool:
        """Подключение к MQTT брокеру с TLS."""
        try:
            # TLS configuration
            self.client.tls_set(
                ca_certs=self.config.ca_cert,
                certfile=self.config.client_cert,
                keyfile=self.config.client_key,
                cert_reqs=mqtt.ssl.CERT_REQUIRED,
                tls_version=mqtt.ssl.PROTOCOL_TLSv1_2,
                ciphers=None
            )

            # Authentication
            self.client.username_pw_set(self.config.username, self.config.password)

            # Connect
            self.client.connect(
                self.config.broker_host,
                self.config.broker_port,
                keepalive=self.config.keep_alive
            )

            # Start network loop
            self.client.loop_start()

            return True

        except Exception as e:
            self.logger.error(f"MQTT connection error: {e}")
            return False

    def publish_telemetry(self, data: Dict) -> bool:
        """
        Публикация данных телеметрии с QoS 2.
        Гарантирует доставку: сервер обязан принять и подтвердить.
        """
        try:
            payload = json.dumps(data)

            # Publish with QoS 2
            info = self.client.publish(
                self.config.telemetry_topic,
                payload,
                qos=self.config.qos_level,
                retain=False
            )

            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                self.pending_acks[info.mid] = {
                    "data": data,
                    "timestamp": time.time()
                }
                self.logger.debug(f"Published (QoS {self.config.qos_level}): {info.mid}")
                return True

            else:
                self.logger.error(f"Publish failed: {info.rc}")
                self.publish_queue.append(data)  # Queue for retry
                return False

        except Exception as e:
            self.logger.error(f"Publish error: {e}")
            self.publish_queue.append(data)
            return False

    def _flush_queue(self):
        """Отправить все queued сообщения при восстановлении связи."""
        while self.publish_queue:
            data = self.publish_queue.pop(0)
            if not self.publish_telemetry(data):
                self.publish_queue.insert(0, data)  # Re-queue
                break

    def disconnect(self):
        """Корректное отключение."""
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("MQTT disconnected")


class SQLiteOfflineBuffer:
    """
    Локальная очередь для данных когда MQTT недоступен.
    Агрегирует данные (среднее, max, min) перед отправкой.
    """

    def __init__(self, db_path: str, logger: logging.Logger):
        self.db_path = db_path
        self.logger = logger
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """SQLite схема с таблицей для агрегированных данных."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Raw telemetry
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                data TEXT NOT NULL,
                delivered INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Aggregated stats (для экономии пропускной способности)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_aggregate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                window_start REAL NOT NULL,
                window_end REAL NOT NULL,
                avg_lat REAL,
                avg_lon REAL,
                avg_depth REAL,
                max_temp REAL,
                min_battery INTEGER,
                record_count INTEGER,
                sent INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    def enqueue(self, data: Dict) -> bool:
        """Добавить данные в очередь."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO telemetry_queue (timestamp, data)
                VALUES (?, ?)
            """, (time.time(), json.dumps(data)))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            self.logger.error(f"Queue enqueue error: {e}")
            return False

    def get_aggregate(self, window_size: float = 60.0) -> Optional[Dict]:
        """
        Получить агрегированные данные за последний период.
        Экономит пропускную способность (например, 60 сек → 1 запись вместо 60).
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            now = time.time()
            window_start = now - window_size

            cursor.execute("""
                SELECT
                    AVG(json_extract(data, '$.lat')) as avg_lat,
                    AVG(json_extract(data, '$.lon')) as avg_lon,
                    AVG(json_extract(data, '$.depth_m')) as avg_depth,
                    MAX(json_extract(data, '$.temperature_c')) as max_temp,
                    MIN(json_extract(data, '$.battery_pct')) as min_battery,
                    COUNT(*) as record_count
                FROM telemetry_queue
                WHERE timestamp >= ? AND timestamp < ? AND delivered = 0
            """, (window_start, now))

            result = cursor.fetchone()
            conn.close()

            if result and result[5] > 0:  # record_count > 0
                return {
                    "avg_lat": result[0],
                    "avg_lon": result[1],
                    "avg_depth_m": result[2],
                    "max_temperature_c": result[3],
                    "min_battery_pct": result[4],
                    "aggregated_records": result[5],
                    "window_size_s": window_size
                }

            return None

        except Exception as e:
            self.logger.error(f"Aggregate query error: {e}")
            return None

    def mark_delivered(self, count: int) -> bool:
        """Отметить записи как доставленные."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE telemetry_queue
                SET delivered = 1
                WHERE id IN (
                    SELECT id FROM telemetry_queue
                    WHERE delivered = 0
                    LIMIT ?
                )
            """, (count,))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            self.logger.error(f"Mark delivered error: {e}")
            return False

    def get_queue_depth(self) -> int:
        """Глубина очереди (сколько неотправленных записей)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM telemetry_queue WHERE delivered = 0")
            count = cursor.fetchone()[0]
            conn.close()

            return count

        except Exception as e:
            self.logger.error(f"Queue depth error: {e}")
            return 0


class HybridTelemetrySystem:
    """
    Гибридная система: MQTT (online) + SQLite (offline) + Aggregation (bandwidth savings).
    Решает проблемы:
    - Firebase Lag → MQTT QoS 2
    - Offline Identity → Graceful degradation
    - Limited bandwidth → Data aggregation
    """

    def __init__(self, mqtt_config: MQTTConfig, db_path: str, logger: logging.Logger):
        self.logger = logger
        self.mqtt = MQTTResiliencyManager(mqtt_config, logger)
        self.buffer = SQLiteOfflineBuffer(db_path, logger)

        self.running = False
        self.sync_thread = None

    def connect(self) -> bool:
        """Инициализировать систему."""
        if self.mqtt.connect_to_broker():
            self.logger.info("Hybrid telemetry system initialized")
            return True
        else:
            self.logger.error("Failed to connect to MQTT broker")
            return False

    def start_sync_loop(self, interval: float = 5.0):
        """Запустить фоновой цикл синхронизации."""
        self.running = True
        self.sync_thread = threading.Thread(
            target=self._sync_loop,
            args=(interval,),
            daemon=True
        )
        self.sync_thread.start()

    def _sync_loop(self, interval: float):
        """Фоновой цикл синхронизации буфера с MQTT."""
        while self.running:
            try:
                # Проверка связи
                is_online = self.mqtt.monitor.check_connectivity()

                if is_online and self.mqtt.is_connected:
                    # Online: отправляем агрегированные данные
                    aggregate = self.buffer.get_aggregate(window_size=60.0)

                    if aggregate:
                        if self.mqtt.publish_telemetry(aggregate):
                            queue_depth = self.buffer.get_queue_depth()
                            self.buffer.mark_delivered(aggregate["aggregated_records"])
                            self.logger.info(
                                f"Synced: {aggregate['aggregated_records']} records, "
                                f"Queue depth: {queue_depth}"
                            )

                else:
                    # Offline: буферизируем локально
                    queue_depth = self.buffer.get_queue_depth()
                    if queue_depth > 100:
                        self.logger.warning(f"Buffer FULL: {queue_depth} records pending")

                time.sleep(interval)

            except Exception as e:
                self.logger.error(f"Sync loop error: {e}")

    def send_telemetry(self, data: Dict) -> bool:
        """Отправить телеметрию (online или offline)."""
        if self.mqtt.monitor.check_connectivity() and self.mqtt.is_connected:
            return self.mqtt.publish_telemetry(data)
        else:
            return self.buffer.enqueue(data)

    def stop(self):
        """Остановить систему."""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        self.mqtt.disconnect()


# ============ Example Usage ============

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger = logging.getLogger("mqtt_resilience")

    # Configure MQTT
    mqtt_config = MQTTConfig(
        broker_host="mqtt.local",  # Or your cloud broker
        broker_port=8883,
        username="rov_user",
        password="secure_pass"
    )

    # Initialize hybrid system
    system = HybridTelemetrySystem(
        mqtt_config=mqtt_config,
        db_path="/app/data/telemetry_offline.db",
        logger=logger
    )

    if system.connect():
        system.start_sync_loop(interval=5.0)

        # Send sample data
        try:
            for i in range(20):
                data = {
                    "timestamp": time.time(),
                    "lat": 34.9821 + i * 0.001,
                    "lon": 33.9512 + i * 0.001,
                    "depth_m": 15.5,
                    "temperature_c": 12.0,
                    "battery_pct": 85,
                    "device_id": "rov-001"
                }
                system.send_telemetry(data)
                time.sleep(1)

        except KeyboardInterrupt:
            pass

        finally:
            system.stop()
