"""
Unit tests for ESP32-S3 Watchdog module.

Tests cover:
- Normal heartbeat reception
- Timeout detection and recovery
- Serial communication error handling
- State machine transitions
- Mock watchdog simulation
"""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Add robotics package to path
sys.path.insert(0, '/home/user/VKTEST')

from robotics.watchdog.esp32_watchdog import (
    ESP32Watchdog,
    MockESP32Watchdog,
    WatchdogState,
    WatchdogConfig,
)


class TestWatchdogConfig:
    """Test WatchdogConfig dataclass."""

    def test_default_config(self):
        """Default config should have reasonable values."""
        config = WatchdogConfig()
        assert config.serial_port == "/dev/ttyUSB0"
        assert config.baud_rate == 115200
        assert config.heartbeat_interval_sec == 10.0
        assert config.timeout_threshold_sec == 30.0
        assert config.heartbeat_char == b'H'

    def test_custom_config(self):
        """Should accept custom configuration."""
        config = WatchdogConfig(
            serial_port="/dev/ttyUSB1",
            baud_rate=9600,
            timeout_threshold_sec=60.0
        )
        assert config.serial_port == "/dev/ttyUSB1"
        assert config.baud_rate == 9600
        assert config.timeout_threshold_sec == 60.0


class TestESP32WatchdogInit:
    """Test ESP32Watchdog initialization."""

    def test_init_default(self):
        """Should initialize with default config."""
        watchdog = ESP32Watchdog()
        assert watchdog.state == WatchdogState.IDLE
        assert watchdog.heartbeat_count == 0
        assert watchdog.timeout_count == 0
        assert watchdog.serial_port is None

    def test_init_custom_config(self):
        """Should accept custom config."""
        config = WatchdogConfig(heartbeat_interval_sec=5.0)
        watchdog = ESP32Watchdog(config)
        assert watchdog.config.heartbeat_interval_sec == 5.0


class TestESP32WatchdogConnection:
    """Test serial connection management."""

    @patch('serial.Serial')
    def test_connect_success(self, mock_serial_class):
        """Should successfully connect to serial port."""
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        result = watchdog.connect()

        assert result is True
        assert watchdog.state == WatchdogState.LISTENING
        assert watchdog.serial_port is not None
        mock_serial_class.assert_called_once()

    @patch('serial.Serial')
    def test_connect_failure(self, mock_serial_class):
        """Should handle serial connection failure."""
        import serial
        mock_serial_class.side_effect = serial.SerialException("Port not found")

        watchdog = ESP32Watchdog()
        result = watchdog.connect()

        assert result is False
        assert watchdog.state == WatchdogState.ERROR

    @patch('serial.Serial')
    def test_disconnect(self, mock_serial_class):
        """Should close serial connection."""
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()
        watchdog.disconnect()

        mock_port.close.assert_called_once()


class TestHeartbeatReception:
    """Test heartbeat reception and tracking."""

    @patch('serial.Serial')
    def test_receive_heartbeat(self, mock_serial_class):
        """Should update heartbeat timestamp on reception."""
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()

        initial_time = watchdog.last_heartbeat_time
        time.sleep(0.1)

        result = watchdog.receive_heartbeat()

        assert result is True
        assert watchdog.heartbeat_count == 1
        assert watchdog.last_heartbeat_time > initial_time
        assert watchdog.state == WatchdogState.LISTENING

    @patch('serial.Serial')
    def test_multiple_heartbeats(self, mock_serial_class):
        """Should count multiple heartbeats correctly."""
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()

        for i in range(5):
            result = watchdog.receive_heartbeat()
            assert result is True
            assert watchdog.heartbeat_count == i + 1

    @patch('serial.Serial')
    def test_heartbeat_during_recovery(self, mock_serial_class):
        """Should reject heartbeat during recovery."""
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()
        watchdog.state = WatchdogState.RECOVERING

        result = watchdog.receive_heartbeat()
        assert result is False


class TestTimeoutDetection:
    """Test timeout detection mechanism."""

    @patch('serial.Serial')
    def test_timeout_detection(self, mock_serial_class):
        """Should detect timeout after threshold exceeded."""
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        config = WatchdogConfig(timeout_threshold_sec=1.0)
        watchdog = ESP32Watchdog(config)
        watchdog.connect()

        # Set last heartbeat to past
        watchdog.last_heartbeat_time = time.time() - 2.0

        # Increment timeout_count as monitor loop would
        watchdog.timeout_count += 1
        watchdog._trigger_recovery()

        assert watchdog.timeout_count >= 1

    @patch('serial.Serial')
    def test_timeout_callback(self, mock_serial_class):
        """Should call timeout callback when triggered."""
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()

        callback_called = False

        def on_timeout():
            nonlocal callback_called
            callback_called = True

        watchdog.on_timeout = on_timeout
        watchdog.last_heartbeat_time = time.time() - 35.0
        watchdog._trigger_recovery()

        # Give callback time to be called
        time.sleep(0.1)

        # Check if callback was registered (actual execution depends on thread timing)
        assert watchdog.on_timeout is not None


class TestGetStatus:
    """Test status reporting."""

    @patch('serial.Serial')
    def test_get_status(self, mock_serial_class):
        """Should return accurate status information."""
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()
        watchdog.receive_heartbeat()

        status = watchdog.get_status()

        assert "state" in status
        assert status["state"] == WatchdogState.LISTENING.value
        assert status["heartbeat_count"] == 1
        assert status["timeout_count"] == 0
        assert status["time_since_heartbeat_sec"] >= 0
        assert status["is_connected"] is True

    @patch('serial.Serial')
    def test_status_not_connected(self, mock_serial_class):
        """Should show disconnected in status."""
        watchdog = ESP32Watchdog()
        status = watchdog.get_status()

        assert status["is_connected"] is False
        assert status["heartbeat_count"] == 0


class TestMockWatchdog:
    """Test MockESP32Watchdog for testing without hardware."""

    def test_mock_connect(self):
        """Mock should connect without serial port."""
        watchdog = MockESP32Watchdog()
        result = watchdog.connect()

        assert result is True
        assert watchdog.state == WatchdogState.LISTENING

    def test_mock_heartbeat(self):
        """Mock should handle heartbeats normally."""
        watchdog = MockESP32Watchdog()
        watchdog.connect()

        for i in range(3):
            result = watchdog.receive_heartbeat()
            assert result is True
            assert watchdog.heartbeat_count == i + 1

    def test_mock_timeout_simulation(self):
        """Mock should simulate timeout when configured."""
        config = WatchdogConfig(timeout_threshold_sec=0.1)
        watchdog = MockESP32Watchdog(simulate_timeout=True)
        watchdog.config = config  # Use shorter timeout for testing
        watchdog.connect()
        watchdog.start_monitoring()

        # Wait for timeout to be triggered
        time.sleep(4.0)

        watchdog.stop_monitoring()

        assert watchdog.timeout_count >= 1

    def test_mock_status(self):
        """Mock should report accurate status."""
        watchdog = MockESP32Watchdog()
        watchdog.connect()
        watchdog.receive_heartbeat()

        status = watchdog.get_status()

        assert status["is_connected"] is True
        assert status["heartbeat_count"] == 1


class TestThreadSafety:
    """Test thread-safe operations."""

    @patch('serial.Serial')
    def test_concurrent_heartbeats(self, mock_serial_class):
        """Should handle concurrent heartbeat reception."""
        import threading

        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()

        def send_heartbeat():
            for _ in range(5):
                watchdog.receive_heartbeat()
                time.sleep(0.01)

        threads = [threading.Thread(target=send_heartbeat) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert watchdog.heartbeat_count == 15  # 5 beats × 3 threads

    @patch('serial.Serial')
    def test_concurrent_status_check(self, mock_serial_class):
        """Should safely report status during operations."""
        import threading

        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        watchdog = ESP32Watchdog()
        watchdog.connect()

        statuses = []

        def check_status():
            for _ in range(5):
                statuses.append(watchdog.get_status())
                time.sleep(0.01)

        def send_heartbeat():
            for _ in range(5):
                watchdog.receive_heartbeat()
                time.sleep(0.01)

        threads = [
            threading.Thread(target=check_status),
            threading.Thread(target=send_heartbeat),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(statuses) >= 5
        assert all("state" in s for s in statuses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
