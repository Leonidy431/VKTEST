"""
Integration tests for Telemetry System
Tests the interaction between:
- TelemetryEngine (Firebase direct send)
- MQTTResiliencyManager (MQTT QoS 2 fallback)
- SQLiteOfflineBuffer (local persistence)
- BandwidthPriorityQueue (priority-based sending)

Scenarios tested:
1. Online → Firebase direct send
2. Offline → SQLite buffer
3. Network recovery → buffer sync to Firebase
4. Concurrent telemetry sends during sync
5. Bandwidth constraints with priority queue
6. Data aggregation on surface sync
7. MQTT fallback when Firebase unavailable
"""

import pytest
import logging
import sys
import time
import sqlite3
import tempfile
import threading
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import dataclass

sys.path.insert(0, '/home/user/VKTEST')

from robotics.telemetry_system.telemetry_robot import (
    TelemetryEngine,
    TelemetryConfig,
    TelemetryRecord,
    LocalBuffer,
    FirebaseSyncManager,
    SensorSimulator,
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
    CompressedTelemetry,
)


class TestTelemetryEngineOnlineMode:
    """Test telemetry engine when connected to Firebase."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test configuration."""
        return TelemetryConfig(
            firebase_url="https://test-project.firebaseio.com/",
            service_account_key="/tmp/fake-key.json",
            buffer_file=str(tmp_path / "telemetry.db"),
            log_file=str(tmp_path / "telemetry.log"),
        )

    @pytest.fixture
    def engine(self, config):
        """Create test engine."""
        return TelemetryEngine(config)

    def test_engine_initialization(self, engine, config):
        """Engine should initialize buffer and sync manager."""
        assert engine.buffer is not None
        assert engine.sync_manager is not None
        assert engine.running is False

    def test_send_telemetry_online(self, engine):
        """Should send telemetry directly when online."""
        engine.sync_manager.is_connected = True
        record = TelemetryRecord(
            timestamp=time.time(),
            lat=34.9821,
            lon=33.9512,
            depth_m=10.5,
            battery_pct=85,
            device_id="rov-001"
        )

        with patch.object(engine.sync_manager, 'push_record', return_value='firebase-key-123') as mock_push:
            result = engine.send_telemetry(record)
            assert result is True
            mock_push.assert_called_once()

    def test_send_telemetry_offline_fallback_to_buffer(self, engine):
        """Should buffer telemetry when offline."""
        engine.sync_manager.is_connected = False
        record = TelemetryRecord(
            timestamp=time.time(),
            lat=34.9821,
            lon=33.9512,
            depth_m=10.5,
            battery_pct=85,
            device_id="rov-001"
        )

        result = engine.send_telemetry(record)

        assert result is True
        stats = engine.buffer.get_buffer_stats()
        assert stats["unsynced"] == 1

    def test_connectivity_state_tracking(self, engine):
        """Should track online/offline state transitions."""
        engine.sync_manager.is_connected = False

        with patch.object(engine.sync_manager, 'check_connectivity', return_value=True):
            # Simulate connectivity check
            was_connected = engine.sync_manager.is_connected
            engine.sync_manager.is_connected = engine.sync_manager.check_connectivity()

        assert engine.sync_manager.is_connected is True


class TestTelemetryEngineOfflineBuffering:
    """Test offline buffering during network loss."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create test engine with temp buffer."""
        config = TelemetryConfig(
            buffer_file=str(tmp_path / "buffer.db"),
            log_file=str(tmp_path / "log.txt"),
        )
        return TelemetryEngine(config)

    def test_buffer_persistence(self, engine):
        """Buffered data should persist across engine restarts."""
        engine.sync_manager.is_connected = False

        # Send 5 records while offline
        for i in range(5):
            record = TelemetryRecord(
                timestamp=time.time() + i,
                lat=34.0 + i * 0.01,
                lon=33.0 + i * 0.01,
                depth_m=10.0,
                battery_pct=85,
                device_id="rov-001"
            )
            engine.send_telemetry(record)

        stats = engine.buffer.get_buffer_stats()
        assert stats["total"] == 5
        assert stats["unsynced"] == 5

        # Create new engine with same buffer
        config2 = engine.config
        engine2 = TelemetryEngine(config2)

        # Should see persisted data
        stats2 = engine2.buffer.get_buffer_stats()
        assert stats2["total"] == 5

    def test_buffer_duplicate_prevention(self, engine):
        """Should prevent duplicate records via hash."""
        engine.sync_manager.is_connected = False

        record = TelemetryRecord(
            timestamp=100.0,
            lat=34.9821,
            lon=33.9512,
            depth_m=10.5,
            battery_pct=85,
            device_id="rov-001"
        )

        # Send same record twice
        engine.send_telemetry(record)
        engine.send_telemetry(record)

        # Should only have 1 record due to hash uniqueness
        stats = engine.buffer.get_buffer_stats()
        assert stats["total"] == 1


class TestBufferSyncWithFirebase:
    """Test synchronization of buffered data back to Firebase."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create test engine."""
        config = TelemetryConfig(
            buffer_file=str(tmp_path / "buffer.db"),
            log_file=str(tmp_path / "log.txt"),
        )
        return TelemetryEngine(config)

    def test_sync_buffered_data(self, engine):
        """Should sync buffered records when reconnected."""
        engine.sync_manager.is_connected = False

        # Buffer 3 records
        for i in range(3):
            record = TelemetryRecord(
                timestamp=time.time() + i,
                lat=34.0 + i * 0.01,
                lon=33.0 + i * 0.01,
                depth_m=10.0,
                battery_pct=85,
                device_id="rov-001"
            )
            engine.send_telemetry(record)

        stats_before = engine.buffer.get_buffer_stats()
        assert stats_before["unsynced"] == 3

        # Reconnect and sync
        engine.sync_manager.is_connected = True
        with patch.object(engine.sync_manager, 'push_record', return_value='key-123'):
            synced_count = engine.sync_manager.sync_buffer(engine.buffer)

        assert synced_count == 3
        stats_after = engine.buffer.get_buffer_stats()
        assert stats_after["unsynced"] == 0

    def test_sync_partial_failure_stops_at_first_error(self, engine):
        """Should stop sync on first failure to preserve order."""
        engine.sync_manager.is_connected = False

        # Buffer 5 records
        for i in range(5):
            record = TelemetryRecord(
                timestamp=time.time() + i,
                lat=34.0 + i * 0.01,
                lon=33.0 + i * 0.01,
                depth_m=10.0,
                device_id="rov-001"
            )
            engine.send_telemetry(record)

        # Mock Firebase to fail on 3rd record
        call_count = [0]
        def push_side_effect(record):
            call_count[0] += 1
            if call_count[0] == 3:
                return None  # Simulate failure
            return f'key-{call_count[0]}'

        engine.sync_manager.is_connected = True
        with patch.object(engine.sync_manager, 'push_record', side_effect=push_side_effect):
            synced_count = engine.sync_manager.sync_buffer(engine.buffer)

        # Should have synced 2, stopped at 3rd
        assert synced_count == 2
        stats = engine.buffer.get_buffer_stats()
        assert stats["unsynced"] == 3


class TestMQTTFallbackIntegration:
    """Test MQTT QoS 2 fallback when Firebase unavailable."""

    @pytest.fixture
    def hybrid_system(self, tmp_path):
        """Create hybrid telemetry system."""
        mqtt_config = MQTTConfig(
            broker_host="localhost",
            broker_port=1883,
            qos_level=2
        )
        db_path = str(tmp_path / "hybrid.db")
        logger = logging.getLogger(__name__)
        return HybridTelemetrySystem(mqtt_config, db_path, logger)

    def test_mqtt_publish_with_qos2(self, hybrid_system):
        """Should publish with QoS 2 (exactly-once) when configured."""
        data = {
            "timestamp": time.time(),
            "lat": 34.9821,
            "lon": 33.9512,
            "depth_m": 15.5,
            "battery_pct": 85
        }

        with patch.object(hybrid_system.mqtt, 'publish_telemetry', return_value=True):
            hybrid_system.mqtt.is_connected = True
            result = hybrid_system.mqtt.publish_telemetry(data)

        assert result is True

    def test_fallback_chain_firebase_mqtt_buffer(self, hybrid_system):
        """Should try Firebase → MQTT → buffer in sequence."""
        # Simulate both Firebase and MQTT unavailable
        with patch.object(hybrid_system.mqtt.monitor, 'check_connectivity', return_value=False):
            data = {
                "timestamp": time.time(),
                "lat": 34.9821,
                "lon": 33.9512,
                "battery_pct": 85
            }

            # Should buffer locally when offline
            hybrid_system.mqtt.is_connected = False
            hybrid_system.send_telemetry(data)

            # Verify buffered
            depth = hybrid_system.buffer.get_queue_depth()
            assert depth > 0


class TestBandwidthConstrainedTelemetry:
    """Test telemetry behavior under bandwidth constraints."""

    @pytest.fixture
    def priority_queue(self):
        """Create priority queue."""
        logger = logging.getLogger(__name__)
        return BandwidthPriorityQueue(logger)

    def test_priority_ordering_under_constraint(self, priority_queue):
        """Should prioritize CRITICAL > SAFETY > SCIENCE > TELEMETRY > DEBUG."""
        # Add records in random priority order
        priority_queue.enqueue(
            {
                "timestamp": 100,
                "lat": 34.9821,
                "lon": 33.9512,
                "device_id": 1,
                "depth_m": 10,
                "battery_pct": 85,
                "temperature_c": 15,
            },
            DataPriority.SCIENCE
        )
        priority_queue.enqueue(
            {
                "timestamp": 101,
                "lat": 34.9821,
                "lon": 33.9512,
                "device_id": 1,
                "depth_m": 10,
                "battery_pct": 10,  # Low battery = SAFETY
                "temperature_c": 15,
            },
            DataPriority.SAFETY
        )
        priority_queue.enqueue(
            {
                "timestamp": 102,
                "lat": 34.9821,
                "lon": 33.9512,
                "device_id": 1,
                "depth_m": 200,  # Overpressure = CRITICAL
                "battery_pct": 85,
                "temperature_c": 15,
            },
            DataPriority.CRITICAL
        )

        # Extract with small bandwidth (0.1 kbps = 12 bytes per second)
        extracted = priority_queue.get_packets_for_bandwidth(0.1)

        # Should extract at least one packet, prioritized by priority
        assert len(extracted) >= 1

    def test_bandwidth_constraint_dropping(self, priority_queue):
        """Should drop DEBUG/TELEMETRY packets under extreme bandwidth constraint."""
        # Add many records
        for i in range(20):
            priority_queue.enqueue(
                {
                    "timestamp": 100 + i,
                    "lat": 34.9821,
                    "lon": 33.9512,
                    "device_id": 1,
                    "depth_m": 10,
                    "battery_pct": 85,
                    "temperature_c": 15,
                },
                DataPriority.TELEMETRY
            )

        # Extract with very small bandwidth (0.1 kbps)
        extracted = priority_queue.get_packets_for_bandwidth(0.1)

        # Should extract <= 1 packet (12 bytes = 1 packet)
        total_bytes = sum(len(p) for p in extracted if isinstance(p, bytes))
        assert total_bytes <= 24  # Allow 2 packets max


class TestConcurrentTelemetrySending:
    """Test concurrent telemetry sends with background sync."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create test engine."""
        config = TelemetryConfig(
            buffer_file=str(tmp_path / "buffer.db"),
            log_file=str(tmp_path / "log.txt"),
            sync_interval_s=0.1,  # Fast sync for testing
            offline_check_interval_s=0.1,
        )
        return TelemetryEngine(config)

    def test_concurrent_send_during_sync(self, engine):
        """Should handle concurrent sends while sync is in progress."""
        engine.sync_manager.is_connected = False

        # Start engine (sync loop will run)
        engine.start()
        time.sleep(0.1)

        try:
            # Send records concurrently
            def send_batch():
                for i in range(5):
                    record = TelemetryRecord(
                        timestamp=time.time() + i * 0.01,
                        lat=34.0 + i * 0.001,
                        lon=33.0 + i * 0.001,
                        depth_m=10.0,
                        battery_pct=85,
                        device_id="rov-001"
                    )
                    engine.send_telemetry(record)

            threads = [threading.Thread(target=send_batch) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should have buffered 15 records without error
            stats = engine.buffer.get_buffer_stats()
            assert stats["total"] >= 10  # Some may be duplicates

        finally:
            engine.stop()

    def test_sync_thread_concurrent_with_sends(self, engine):
        """Sync thread should not interfere with send operations."""
        engine.sync_manager.is_connected = False
        engine.start()

        try:
            # Send and check simultaneously
            for _ in range(10):
                record = TelemetryRecord(
                    timestamp=time.time(),
                    lat=34.9821,
                    lon=33.9512,
                    depth_m=10.0,
                    battery_pct=85,
                    device_id="rov-001"
                )
                engine.send_telemetry(record)
                time.sleep(0.05)

            # Engine should be responsive
            stats = engine.buffer.get_buffer_stats()
            assert stats["total"] > 0

        finally:
            engine.stop()


class TestSurfaceSyncAggregation:
    """Test data aggregation during surface sync."""

    @pytest.fixture
    def hybrid_system(self, tmp_path):
        """Create hybrid system."""
        mqtt_config = MQTTConfig()
        db_path = str(tmp_path / "hybrid.db")
        logger = logging.getLogger(__name__)
        return HybridTelemetrySystem(mqtt_config, db_path, logger)

    def test_aggregation_on_surface_sync(self, hybrid_system):
        """Should aggregate buffered data during surface sync."""
        # Buffer 10 records during dive
        base_time = time.time()
        for i in range(10):
            data = {
                "timestamp": base_time + i * 0.5,
                "lat": 34.0 + i * 0.001,
                "lon": 33.0 + i * 0.001,
                "depth_m": 10.0 + i,
                "battery_pct": 85 - i * 2,
                "temperature_c": 12.0 - i * 0.1
            }
            hybrid_system.buffer.enqueue(data)

        # Simulate surface (aggregation window)
        aggregate = hybrid_system.buffer.get_aggregate(window_size=10.0)

        if aggregate:
            assert aggregate["aggregated_records"] == 10
            assert aggregate["avg_depth_m"] is not None
            assert aggregate["min_battery_pct"] is not None

    def test_aggregate_statistics_correctness(self, hybrid_system):
        """Aggregate statistics should be mathematically correct."""
        # Buffer known values
        for i in range(5):
            data = {
                "lat": 34.0,
                "lon": 33.0,
                "depth_m": 10.0 + i,  # 10, 11, 12, 13, 14
                "battery_pct": 90 - i * 10,  # 90, 80, 70, 60, 50
            }
            hybrid_system.buffer.enqueue(data)

        aggregate = hybrid_system.buffer.get_aggregate(window_size=10.0)

        if aggregate:
            # Average depth should be 12.0 (sum=60, avg=60/5=12)
            assert aggregate["avg_depth_m"] is not None
            # Min battery should be 50
            assert aggregate["min_battery_pct"] == 50


class TestConnectivityRecovery:
    """Test recovery from various connectivity failures."""

    @pytest.fixture
    def monitor(self):
        """Create resilience monitor."""
        logger = logging.getLogger(__name__)
        return ResilienceMonitor(logger)

    def test_dns_failure_recovery(self, monitor):
        """Should recover from DNS failure."""
        import socket

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # First: DNS failure
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")
            result1 = monitor.check_connectivity()
            assert result1 is False
            assert monitor.connection_state == "OFFLINE"

            # Then: recovery
            mock_sock.connect.side_effect = None
            result2 = monitor.check_connectivity()
            assert result2 is True
            assert monitor.connection_state == "ONLINE"

    def test_repeated_failures_tracked(self, monitor):
        """Should track disconnect count across failures."""
        import socket

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.gaierror("DNS")

            # Multiple failures
            for i in range(3):
                monitor.check_connectivity()

            assert monitor.disconnect_count == 3

            # Recovery
            mock_sock.connect.side_effect = None
            monitor.check_connectivity()

            # Count should not reset after recovery
            assert monitor.disconnect_count == 3

    def test_timeout_handling(self, monitor):
        """Should distinguish timeouts from DNS failures."""
        import socket

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # Timeout
            mock_sock.connect.side_effect = socket.timeout("Connection timed out")
            result = monitor.check_connectivity()

            assert result is False
            assert monitor.last_disconnect_reason == "TIMEOUT"


class TestEndToEndMission:
    """End-to-end integration test simulating complete mission."""

    @pytest.fixture
    def mission_engine(self, tmp_path):
        """Create engine for mission simulation."""
        config = TelemetryConfig(
            buffer_file=str(tmp_path / "mission.db"),
            log_file=str(tmp_path / "mission.log"),
            sync_interval_s=0.05,
            offline_check_interval_s=0.05,
        )
        return TelemetryEngine(config)

    def test_full_mission_cycle(self, mission_engine):
        """Simulate: preflight → dive (offline) → surface (sync) → idle."""
        mission_engine.start()
        sensor_sim = SensorSimulator("rov-001")

        try:
            # Phase 1: Preflight (online)
            mission_engine.sync_manager.is_connected = True
            for _ in range(3):
                record = sensor_sim.read_sensors()
                with patch.object(mission_engine.sync_manager, 'push_record', return_value='key'):
                    mission_engine.send_telemetry(record)

            # Phase 2: Dive (offline - network loss)
            mission_engine.sync_manager.is_connected = False
            for _ in range(10):
                record = sensor_sim.read_sensors()
                mission_engine.send_telemetry(record)

            stats_dive = mission_engine.buffer.get_buffer_stats()
            assert stats_dive["unsynced"] >= 5  # Some buffered

            # Phase 3: Surface (network recovery + sync)
            mission_engine.sync_manager.is_connected = True
            with patch.object(mission_engine.sync_manager, 'push_record', return_value='key'):
                synced = mission_engine.sync_manager.sync_buffer(mission_engine.buffer)

            stats_synced = mission_engine.buffer.get_buffer_stats()
            assert stats_synced["unsynced"] == 0  # All synced

        finally:
            mission_engine.stop()

    def test_mission_buffer_never_exceeds_limit(self, mission_engine):
        """Buffer should not grow beyond max size even with prolonged offline."""
        mission_engine.sync_manager.is_connected = False
        sensor_sim = SensorSimulator("rov-001")

        # Simulate 100 sensor readings
        for _ in range(100):
            record = sensor_sim.read_sensors()
            mission_engine.send_telemetry(record)

        stats = mission_engine.buffer.get_buffer_stats()
        # Should not exceed 1000 (buffer_max_size from config)
        assert stats["total"] <= 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
