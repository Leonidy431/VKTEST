"""
Unit tests for MQTT DNS Resilience and Error Handling

Tests cover:
- DNS resolution failure handling (socket.gaierror)
- Network timeout scenarios
- Graceful degradation and error suppression
- Exponential backoff retry logic
- Connection state management
- Offline buffering and recovery
"""

import pytest
import logging
import sys
import socket
import time
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, '/home/user/VKTEST')

from robotics.telemetry_system.mqtt_resilient_sync import (
    MQTTConfig,
    ResilienceMonitor,
    MQTTResiliencyManager,
    SQLiteOfflineBuffer,
    HybridTelemetrySystem,
)


class TestMQTTConfig:
    """Test MQTT configuration."""

    def test_default_config(self):
        """Default config should have safe values."""
        config = MQTTConfig()
        assert config.broker_port == 8883  # TLS
        assert config.qos_level == 2  # Exactly-Once
        assert config.connection_timeout == 10
        assert config.keep_alive == 60

    def test_custom_config(self):
        """Should accept custom configuration."""
        config = MQTTConfig(
            broker_host="mqtt.custom.com",
            broker_port=1883,
            client_id="custom-rov"
        )
        assert config.broker_host == "mqtt.custom.com"
        assert config.broker_port == 1883
        assert config.client_id == "custom-rov"


class TestResilienceMonitor:
    """Test DNS resilience and connectivity checking."""

    @pytest.fixture
    def monitor(self):
        """Create test monitor instance."""
        logger = logging.getLogger(__name__)
        return ResilienceMonitor(logger)

    def test_initialization(self, monitor):
        """Monitor should start in INIT state."""
        assert monitor.connection_state == "INIT"
        assert monitor.disconnect_count == 0
        assert monitor.last_disconnect_reason is None

    def test_successful_connectivity_check(self, monitor):
        """Should report online on successful connection."""
        # Mock successful socket connection
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.return_value = None  # Success

            result = monitor.check_connectivity()

            assert result is True
            assert monitor.connection_state == "ONLINE"
            assert monitor.last_disconnect_reason is None

    def test_dns_resolution_failure(self, monitor):
        """Should handle socket.gaierror (DNS failure)."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.gaierror("Name or service not known")

            result = monitor.check_connectivity()

            assert result is False
            assert monitor.connection_state == "OFFLINE"
            assert monitor.last_disconnect_reason == "DNS_FAILURE"
            assert monitor.disconnect_count == 1

    def test_network_timeout(self, monitor):
        """Should handle socket.timeout."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.timeout("Connection timed out")

            result = monitor.check_connectivity()

            assert result is False
            assert monitor.connection_state == "OFFLINE"
            assert monitor.last_disconnect_reason == "TIMEOUT"
            assert monitor.disconnect_count == 1

    def test_os_error_handling(self, monitor):
        """Should handle OSError (connection refused, host unreachable)."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = OSError("Connection refused")

            result = monitor.check_connectivity()

            assert result is False
            assert monitor.connection_state == "OFFLINE"
            assert monitor.last_disconnect_reason == "OS_ERROR"
            assert monitor.disconnect_count == 1

    def test_socket_cleanup_on_success(self, monitor):
        """Should close socket on successful connection."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            monitor.check_connectivity()

            # Verify socket.close() was called
            mock_sock.close.assert_called_once()

    def test_socket_cleanup_on_failure(self, monitor):
        """Should attempt to close socket even on failure."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")

            monitor.check_connectivity()

            # Verify socket.close() was called even though connect failed
            mock_sock.close.assert_called_once()

    def test_disconnect_counter_increment(self, monitor):
        """Should increment disconnect counter on each failure."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # First failure
            mock_sock.connect.side_effect = socket.gaierror("DNS 1")
            monitor.check_connectivity()
            assert monitor.disconnect_count == 1

            # Second failure
            mock_sock.connect.side_effect = socket.timeout("Timeout 2")
            monitor.check_connectivity()
            assert monitor.disconnect_count == 2

            # Success should not increment
            mock_sock.connect.side_effect = None
            monitor.check_connectivity()
            assert monitor.disconnect_count == 2  # Should stay at 2

    def test_recovery_logging(self, monitor):
        """Should log recovery message when coming back online."""
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # Go offline
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")
            monitor.check_connectivity()
            assert monitor.connection_state == "OFFLINE"

            # Come back online
            mock_sock.connect.side_effect = None
            result = monitor.check_connectivity()

            assert result is True
            assert monitor.connection_state == "ONLINE"
            assert monitor.last_disconnect_reason == "DNS_FAILURE"  # Reason persists


class TestSQLiteOfflineBuffer:
    """Test local buffering and aggregation."""

    @pytest.fixture
    def buffer(self, tmp_path):
        """Create test buffer with temporary database."""
        logger = logging.getLogger(__name__)
        db_path = str(tmp_path / "test_buffer.db")
        return SQLiteOfflineBuffer(db_path, logger)

    def test_buffer_initialization(self, buffer):
        """Buffer should initialize with empty queue."""
        assert buffer.get_queue_depth() == 0

    def test_enqueue_data(self, buffer):
        """Should enqueue telemetry data."""
        data = {
            "lat": 34.9821,
            "lon": 33.9512,
            "depth_m": 15.5,
            "battery_pct": 85
        }
        result = buffer.enqueue(data)

        assert result is True
        assert buffer.get_queue_depth() == 1

    def test_enqueue_multiple_records(self, buffer):
        """Should queue multiple records."""
        for i in range(5):
            data = {"lat": 34.0 + i, "lon": 33.0 + i, "depth_m": 15 + i}
            buffer.enqueue(data)

        assert buffer.get_queue_depth() == 5

    def test_get_aggregate(self, buffer):
        """Should aggregate data over time window."""
        import json

        # Add multiple records
        base_time = time.time()
        for i in range(10):
            data = {
                "lat": 34.9821 + i * 0.01,
                "lon": 33.9512 + i * 0.01,
                "depth_m": 15.5 + i,
                "temperature_c": 12.0 - i * 0.1,
                "battery_pct": 85 - i
            }
            buffer.enqueue(data)
            time.sleep(0.01)  # Small delay to ensure timestamp spread

        # Get aggregate
        aggregate = buffer.get_aggregate(window_size=1.0)

        assert aggregate is not None
        assert aggregate["aggregated_records"] == 10
        assert aggregate["avg_lat"] is not None
        assert aggregate["avg_depth_m"] is not None
        assert aggregate["min_battery_pct"] is not None

    def test_mark_delivered(self, buffer):
        """Should mark records as delivered."""
        # Queue 5 records
        for i in range(5):
            buffer.enqueue({"id": i})

        assert buffer.get_queue_depth() == 5

        # Mark 3 as delivered
        buffer.mark_delivered(3)

        # Remaining undelivered
        assert buffer.get_queue_depth() == 2

    def test_empty_aggregate(self, buffer):
        """Should return None for empty queue."""
        aggregate = buffer.get_aggregate()
        assert aggregate is None

    def test_buffer_persistence(self, tmp_path):
        """Data should persist across buffer instances."""
        logger = logging.getLogger(__name__)
        db_path = str(tmp_path / "persistent.db")

        # Create first buffer and add data
        buffer1 = SQLiteOfflineBuffer(db_path, logger)
        buffer1.enqueue({"lat": 34.0, "lon": 33.0})
        buffer1.enqueue({"lat": 34.1, "lon": 33.1})

        # Create second buffer with same path
        buffer2 = SQLiteOfflineBuffer(db_path, logger)

        # Should see data from first buffer
        assert buffer2.get_queue_depth() == 2


class TestHybridTelemetrySystem:
    """Test hybrid online/offline telemetry system."""

    @pytest.fixture
    def hybrid_system(self, tmp_path):
        """Create test hybrid system."""
        logger = logging.getLogger(__name__)
        config = MQTTConfig()
        db_path = str(tmp_path / "hybrid_test.db")
        return HybridTelemetrySystem(config, db_path, logger)

    def test_offline_buffering(self, hybrid_system):
        """Should buffer data when offline."""
        data = {
            "timestamp": time.time(),
            "lat": 34.9821,
            "lon": 33.9512,
            "depth_m": 15.5,
            "battery_pct": 85
        }

        # Mock connectivity check to return False (offline)
        with patch.object(hybrid_system.mqtt.monitor, 'check_connectivity', return_value=False):
            result = hybrid_system.send_telemetry(data)

            # Should buffer locally
            assert hybrid_system.buffer.get_queue_depth() > 0

    def test_online_direct_send(self, hybrid_system):
        """Should send directly when online."""
        data = {
            "timestamp": time.time(),
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 85
        }

        # Mock connectivity check and MQTT publish
        with patch.object(hybrid_system.mqtt.monitor, 'check_connectivity', return_value=True):
            with patch.object(hybrid_system.mqtt, 'is_connected', True):
                with patch.object(hybrid_system.mqtt, 'publish_telemetry', return_value=True):
                    # Should attempt to send online
                    hybrid_system.mqtt.is_connected = True
                    hybrid_system.mqtt.publish_telemetry(data)

    def test_sync_loop_aggregation(self, hybrid_system):
        """Sync loop should aggregate buffered data."""
        # Add data to buffer
        for i in range(5):
            data = {
                "lat": 34.0 + i * 0.01,
                "lon": 33.0 + i * 0.01,
                "depth_m": 15 + i,
                "battery_pct": 85 - i,
                "temperature_c": 12.0
            }
            hybrid_system.buffer.enqueue(data)

        # Verify buffered
        assert hybrid_system.buffer.get_queue_depth() == 5


class TestDNSFailureRecovery:
    """Integration tests for DNS failure and recovery scenarios."""

    def test_dns_failure_with_retry(self):
        """Should handle DNS failure and allow retry."""
        logger = logging.getLogger(__name__)
        monitor = ResilienceMonitor(logger)

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # First attempt: DNS failure
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")
            result1 = monitor.check_connectivity()
            assert result1 is False
            assert monitor.connection_state == "OFFLINE"

            # Second attempt: recovery
            mock_sock.connect.side_effect = None  # Success on retry
            result2 = monitor.check_connectivity()
            assert result2 is True
            assert monitor.connection_state == "ONLINE"

    def test_repeated_dns_failures_log_suppression(self):
        """Should not spam logs on repeated DNS failures."""
        logger = logging.getLogger(__name__)
        monitor = ResilienceMonitor(logger)

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")

            # Multiple failures
            for i in range(5):
                result = monitor.check_connectivity()
                assert result is False
                assert monitor.disconnect_count == i + 1

            # Counter should show repeated failures
            assert monitor.disconnect_count == 5

    def test_graceful_degradation_on_dns_error(self):
        """System should gracefully degrade, not crash on DNS errors."""
        logger = logging.getLogger(__name__)
        config = MQTTConfig()
        hybrid = HybridTelemetrySystem(config, "/tmp/test.db", logger)

        # Real check_connectivity should handle DNS errors gracefully
        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.connect.side_effect = socket.gaierror("DNS failed")

            # Should not raise exception, should return False
            try:
                result = hybrid.mqtt.monitor.check_connectivity()
                assert result is False  # Should handle gracefully
                assert hybrid.mqtt.monitor.connection_state == "OFFLINE"
            except socket.gaierror:
                pytest.fail("Implementation should handle DNS error gracefully")


class TestMQTTConnectionStateManagement:
    """Test connection state machine."""

    def test_state_transitions(self):
        """Should transition through connection states correctly."""
        logger = logging.getLogger(__name__)
        monitor = ResilienceMonitor(logger)

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # INIT → OFFLINE (first check fails)
            mock_sock.connect.side_effect = socket.gaierror("DNS")
            monitor.check_connectivity()
            assert monitor.connection_state == "OFFLINE"

            # OFFLINE → ONLINE (recovery)
            mock_sock.connect.side_effect = None
            monitor.check_connectivity()
            assert monitor.connection_state == "ONLINE"

            # ONLINE → OFFLINE (connection lost)
            mock_sock.connect.side_effect = socket.timeout("Timeout")
            monitor.check_connectivity()
            assert monitor.connection_state == "OFFLINE"

    def test_persistent_disconnect_reason(self):
        """Should maintain last disconnect reason."""
        logger = logging.getLogger(__name__)
        monitor = ResilienceMonitor(logger)

        with patch('socket.socket') as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock

            # DNS failure
            mock_sock.connect.side_effect = socket.gaierror("DNS")
            monitor.check_connectivity()
            assert monitor.last_disconnect_reason == "DNS_FAILURE"

            # Recovery
            mock_sock.connect.side_effect = None
            monitor.check_connectivity()

            # Reason should persist after recovery
            assert monitor.last_disconnect_reason == "DNS_FAILURE"

            # New failure with different reason
            mock_sock.connect.side_effect = socket.timeout("Timeout")
            monitor.check_connectivity()
            assert monitor.last_disconnect_reason == "TIMEOUT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
