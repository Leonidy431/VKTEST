"""
Comprehensive coverage enhancement tests for telemetry system
Targets 99%+ coverage of:
- robotics/telemetry_system/mqtt_resilient_sync.py
- robotics/telemetry_system/telemetry_robot.py
- robotics/telemetry_system/bandwidth_priority_encoder.py
"""

import pytest
import logging
import sys
import time
import sqlite3
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock, call

sys.path.insert(0, '/home/user/VKTEST')

from robotics.telemetry_system.telemetry_robot import (
    TelemetryEngine,
    TelemetryConfig,
    TelemetryRecord,
    LocalBuffer,
    FirebaseSyncManager,
    SensorSimulator,
    setup_logger,
)
from robotics.telemetry_system.mqtt_resilient_sync import (
    MQTTConfig,
    MQTTResiliencyManager,
    SQLiteOfflineBuffer,
    HybridTelemetrySystem,
    ResilienceMonitor,
)
from robotics.telemetry_system.bandwidth_priority_encoder import (
    DataPriority,
    BandwidthPriorityQueue,
    BandwidthAdaptiveEncoder,
    BandwidthMode,
    CompressedTelemetry,
)


# ============ TelemetryRecord Coverage ============

class TestTelemetryRecordCoverage:
    """Complete TelemetryRecord coverage."""

    def test_record_to_dict_excludes_none_values(self):
        """Should exclude None values when converting to dict."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            compass_heading_deg=None,  # None should be excluded
            velocity_ms=None,
            sonar_distance_m=None,
            acoustic_detection=None
        )
        data_dict = record.to_dict()

        assert "compass_heading_deg" not in data_dict
        assert "velocity_ms" not in data_dict
        assert "sonar_distance_m" not in data_dict
        assert "acoustic_detection" not in data_dict
        assert data_dict["lat"] == 34.0

    def test_record_to_dict_includes_values(self):
        """Should include non-None values."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            compass_heading_deg=45.5,
            velocity_ms=1.2,
            sonar_distance_m=50.0
        )
        data_dict = record.to_dict()

        assert data_dict["compass_heading_deg"] == 45.5
        assert data_dict["velocity_ms"] == 1.2
        assert data_dict["sonar_distance_m"] == 50.0

    def test_record_to_json(self):
        """Should serialize to JSON."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            depth_m=15.5,
            battery_pct=85
        )
        json_str = record.to_json()

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["lat"] == 34.0
        assert data["depth_m"] == 15.5


# ============ LocalBuffer Coverage ============

class TestLocalBufferCoverage:
    """Complete LocalBuffer coverage."""

    @pytest.fixture
    def buffer(self, tmp_path):
        """Create test buffer."""
        logger = logging.getLogger(__name__)
        return LocalBuffer(str(tmp_path / "buffer.db"), logger)

    def test_buffer_save_and_retrieve(self, buffer):
        """Should save and retrieve records."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            depth_m=10.0,
            battery_pct=85
        )

        assert buffer.save(record) is True

        unsynced = buffer.get_unsync_records()
        assert len(unsynced) == 1
        assert unsynced[0]["data"]["lat"] == 34.0

    def test_buffer_mark_synced_updates_status(self, buffer):
        """Should mark records as synced."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            battery_pct=85
        )
        buffer.save(record)

        unsynced_before = buffer.get_unsync_records()
        record_id = unsynced_before[0]["id"]

        assert buffer.mark_synced([record_id]) is True

        unsynced_after = buffer.get_unsync_records()
        assert len(unsynced_after) == 0

    def test_buffer_stats_accuracy(self, buffer):
        """Should accurately report buffer statistics."""
        for i in range(5):
            record = TelemetryRecord(
                timestamp=100.0 + i,
                lat=34.0 + i * 0.01,
                lon=33.0 + i * 0.01,
                battery_pct=85 - i * 5
            )
            buffer.save(record)

        stats = buffer.get_buffer_stats()
        assert stats["total"] == 5
        assert stats["unsynced"] == 5

    def test_buffer_error_handling_on_save(self, buffer):
        """Should handle save errors gracefully."""
        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            record = TelemetryRecord(
                timestamp=100.0,
                lat=34.0,
                lon=33.0
            )
            assert buffer.save(record) is False

    def test_buffer_error_handling_on_read(self, buffer):
        """Should handle read errors gracefully."""
        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            records = buffer.get_unsync_records()
            assert records == []

    def test_buffer_error_handling_on_update(self, buffer):
        """Should handle update errors gracefully."""
        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            result = buffer.mark_synced([1])
            assert result is False

    def test_buffer_error_handling_on_stats(self, buffer):
        """Should handle stats query errors gracefully."""
        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            stats = buffer.get_buffer_stats()
            assert stats == {"total": 0, "unsynced": 0}


# ============ FirebaseSyncManager Coverage ============

class TestFirebaseSyncManagerCoverage:
    """Complete FirebaseSyncManager coverage."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return TelemetryConfig(
            firebase_url="https://test.firebaseio.com/",
            service_account_key="/tmp/fake.json",
            buffer_file=str(tmp_path / "buffer.db"),
            log_file=str(tmp_path / "log.txt")
        )

    @pytest.fixture
    def manager(self, config):
        """Create test manager."""
        return FirebaseSyncManager(config, logging.getLogger(__name__))

    def test_check_connectivity_success(self, manager):
        """Should detect successful connectivity."""
        with patch('socket.create_connection', return_value=MagicMock()):
            assert manager.check_connectivity() is True

    def test_check_connectivity_failure(self, manager):
        """Should detect connectivity failure."""
        with patch('socket.create_connection', side_effect=OSError("Network error")):
            assert manager.check_connectivity() is False

    def test_push_record_success(self, manager):
        """Should push record to Firebase."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            device_id="rov-001"
        )

        with patch('firebase_admin.db.reference') as mock_ref:
            mock_push = MagicMock()
            mock_push.key = "firebase-key-123"
            mock_ref.return_value.push.return_value = mock_push

            result = manager.push_record(record)
            assert result == "firebase-key-123"

    def test_push_record_failure(self, manager):
        """Should handle push failure."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0
        )

        with patch('firebase_admin.db.reference', side_effect=Exception("Firebase error")):
            result = manager.push_record(record)
            assert result is None

    def test_get_robot_status_success(self, manager):
        """Should retrieve robot status."""
        with patch('firebase_admin.db.reference') as mock_ref:
            mock_ref.return_value.get.return_value = {"state": "online"}

            result = manager.get_robot_status("rov-001")
            assert result == {"state": "online"}

    def test_get_robot_status_failure(self, manager):
        """Should handle status retrieval failure."""
        with patch('firebase_admin.db.reference', side_effect=Exception("Firebase error")):
            result = manager.get_robot_status("rov-001")
            assert result is None

    def test_update_robot_status_success(self, manager):
        """Should update robot status."""
        with patch('firebase_admin.db.reference') as mock_ref:
            manager.update_robot_status("rov-001", "diving")
            mock_ref.return_value.set.assert_called_once()

    def test_update_robot_status_failure(self, manager):
        """Should handle status update failure."""
        with patch('firebase_admin.db.reference', side_effect=Exception("Firebase error")):
            # Should not raise, just log
            manager.update_robot_status("rov-001", "diving")


# ============ TelemetryEngine Lifecycle Coverage ============

class TestTelemetryEngineLifecycle:
    """Complete TelemetryEngine lifecycle coverage."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create test engine."""
        config = TelemetryConfig(
            buffer_file=str(tmp_path / "buffer.db"),
            log_file=str(tmp_path / "log.txt"),
            sync_interval_s=0.05,
            offline_check_interval_s=0.05
        )
        return TelemetryEngine(config)

    def test_engine_start_creates_threads(self, engine):
        """Engine should create background threads on start."""
        engine.start()
        try:
            assert engine.running is True
            assert len(engine.threads) >= 2
        finally:
            engine.stop()

    def test_engine_stop_halts_threads(self, engine):
        """Engine should stop threads on stop."""
        engine.start()
        time.sleep(0.1)
        engine.stop()

        assert engine.running is False

    def test_send_telemetry_returns_true(self, engine):
        """Should return True for valid telemetry."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0,
            battery_pct=85
        )

        result = engine.send_telemetry(record)
        assert result is True

    def test_send_telemetry_exception_handling(self, engine):
        """Should handle send exceptions gracefully."""
        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.0,
            lon=33.0
        )

        with patch.object(engine.sync_manager, 'push_record', side_effect=Exception("Error")):
            result = engine.send_telemetry(record)
            # Should buffer when exception occurs
            assert result is True
            assert engine.buffer.get_buffer_stats()["total"] > 0


# ============ SensorSimulator Coverage ============

class TestSensorSimulator:
    """Complete SensorSimulator coverage."""

    def test_sensor_simulator_initialization(self):
        """Should initialize sensor simulator."""
        sim = SensorSimulator("rov-001")

        assert sim.device_id == "rov-001"
        assert sim.depth == 0.0
        assert sim.counter == 0

    def test_sensor_simulator_diving_profile(self):
        """Should simulate diving and surfacing profile."""
        sim = SensorSimulator("rov-001")

        # Simulate 50 readings (diving phase)
        for i in range(50):
            record = sim.read_sensors()
            assert record.depth_m >= 0
            assert record.depth_m <= 20
            assert record.temperature_c >= 15.0

    def test_sensor_simulator_cycling(self):
        """Should cycle through diving/surfacing phases."""
        sim = SensorSimulator("rov-001")

        # Go through 2 full cycles
        for _ in range(200):
            record = sim.read_sensors()
            assert record.device_id == "rov-001"
            assert record.battery_pct >= 10
            assert record.battery_pct <= 100


# ============ MQTTResiliencyManager Coverage ============

class TestMQTTResiliencyManagerCoverage:
    """Complete MQTTResiliencyManager coverage."""

    @pytest.fixture
    def manager(self):
        """Create test manager."""
        config = MQTTConfig()
        logger = logging.getLogger(__name__)
        return MQTTResiliencyManager(config, logger)

    def test_manager_initialization(self, manager):
        """Should initialize manager."""
        assert manager.is_connected is False
        assert manager.monitor is not None

    def test_manager_connectivity_check(self, manager):
        """Should check connectivity."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.return_value = None  # Success
            result = manager.monitor.check_connectivity()
            assert result is True


# ============ BandwidthPriorityQueue Coverage ============

class TestBandwidthPriorityQueueCoverage:
    """Complete BandwidthPriorityQueue coverage."""

    @pytest.fixture
    def queue(self):
        """Create test queue."""
        logger = logging.getLogger(__name__)
        return BandwidthPriorityQueue(logger)

    def test_queue_stats(self, queue):
        """Should provide queue statistics."""
        queue.enqueue({
            "timestamp": 100,
            "lat": 34.0,
            "lon": 33.0,
            "depth_m": 10,
            "battery_pct": 85,
            "temperature_c": 15
        }, DataPriority.CRITICAL)

        stats = queue.get_stats()
        assert stats["queue_depth"] == 1
        assert stats["bytes_sent_total"] >= 0

    def test_queue_with_various_modes(self, queue):
        """Should handle all bandwidth modes."""
        # Add packets
        for i in range(5):
            queue.enqueue({
                "lat": 34.0,
                "lon": 33.0,
                "depth_m": 10,
                "battery_pct": 85,
                "temperature_c": 15
            }, DataPriority.TELEMETRY)

        # Test each mode
        packets_luxe = queue.get_packets_for_bandwidth(200.0)  # LUXE mode
        packets_normal = queue.get_packets_for_bandwidth(50.0)  # NORMAL mode
        packets_constrained = queue.get_packets_for_bandwidth(5.0)  # CONSTRAINED mode
        packets_critical = queue.get_packets_for_bandwidth(0.5)  # CRITICAL mode

        # Each should return some packets or handle gracefully
        assert isinstance(packets_luxe, list)
        assert isinstance(packets_normal, list)
        assert isinstance(packets_constrained, list)
        assert isinstance(packets_critical, list)


# ============ BandwidthAdaptiveEncoder Coverage ============

class TestBandwidthAdaptiveEncoderCoverage:
    """Complete BandwidthAdaptiveEncoder coverage."""

    @pytest.fixture
    def encoder(self):
        """Create test encoder."""
        logger = logging.getLogger(__name__)
        return BandwidthAdaptiveEncoder(logger)

    def test_encoder_submit_data(self, encoder):
        """Should submit data to encoder."""
        encoder.submit_data({
            "lat": 34.0,
            "lon": 33.0,
            "depth_m": 10
        }, DataPriority.SCIENCE)

        stats = encoder.queue.get_stats()
        assert stats["queue_depth"] == 1

    def test_encoder_submit_critical(self, encoder):
        """Should submit critical data."""
        encoder.submit_critical((34.0, 33.0), 85, time.time())

        stats = encoder.queue.get_stats()
        assert stats["queue_depth"] >= 1


# ============ SQLiteOfflineBuffer Coverage ============

class TestSQLiteOfflineBufferCoverage:
    """Complete SQLiteOfflineBuffer coverage."""

    @pytest.fixture
    def buffer(self, tmp_path):
        """Create test buffer."""
        logger = logging.getLogger(__name__)
        db_path = str(tmp_path / "offline.db")
        return SQLiteOfflineBuffer(db_path, logger)

    def test_buffer_enqueue_dequeue(self, buffer):
        """Should enqueue and dequeue data."""
        data = {
            "lat": 34.0,
            "lon": 33.0,
            "depth_m": 10
        }

        assert buffer.enqueue(data) is True
        assert buffer.get_queue_depth() == 1

    def test_buffer_mark_delivered(self, buffer):
        """Should mark data as delivered."""
        for i in range(3):
            buffer.enqueue({"lat": 34.0 + i, "lon": 33.0 + i})

        assert buffer.get_queue_depth() == 3
        buffer.mark_delivered(1)
        assert buffer.get_queue_depth() == 2

    def test_buffer_aggregation_empty(self, buffer):
        """Should return None for empty buffer."""
        aggregate = buffer.get_aggregate()
        assert aggregate is None

    def test_buffer_aggregation_with_data(self, buffer):
        """Should aggregate data."""
        for i in range(3):
            buffer.enqueue({
                "lat": 34.0 + i * 0.01,
                "lon": 33.0 + i * 0.01,
                "depth_m": 10.0 + i,
                "battery_pct": 85 - i * 5,
                "temperature_c": 15.0 - i * 0.5
            })

        aggregate = buffer.get_aggregate(window_size=10.0)
        assert aggregate is not None
        assert "aggregated_records" in aggregate


# ============ HybridTelemetrySystem Coverage ============

class TestHybridTelemetrySystemCoverage:
    """Complete HybridTelemetrySystem coverage."""

    @pytest.fixture
    def hybrid(self, tmp_path):
        """Create test hybrid system."""
        config = MQTTConfig()
        db_path = str(tmp_path / "hybrid.db")
        logger = logging.getLogger(__name__)
        return HybridTelemetrySystem(config, db_path, logger)

    def test_hybrid_send_telemetry(self, hybrid):
        """Should send telemetry."""
        data = {
            "timestamp": time.time(),
            "lat": 34.0,
            "lon": 33.0,
            "depth_m": 10
        }

        with patch.object(hybrid.mqtt, 'is_connected', True):
            hybrid.send_telemetry(data)
            # Should complete without error


# ============ Setup Logger Coverage ============

class TestSetupLogger:
    """Complete setup_logger coverage."""

    def test_logger_creation(self, tmp_path):
        """Should create logger with handlers."""
        config = TelemetryConfig(
            log_file=str(tmp_path / "test.log")
        )

        logger = setup_logger(config)

        assert logger is not None
        assert len(logger.handlers) >= 2  # File + Stream handlers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
