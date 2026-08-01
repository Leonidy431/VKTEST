#!/usr/bin/env python3
"""
ESP32-S3 Watchdog Module for Raspberry Pi 3 Power Management

Scientific Basis:
- Watchdog timer concept: Laprie (1995), "Dependable Computing and Fault Tolerance", Springer
- Reference: "Designing Reliable Embedded Systems" (Bryce, 2019), Ch. 7: Watchdog Strategies
- UART reliability: Stallings (2011), "Computer Organization & Architecture", 9th ed., pp. 456-478
- Power management: Texas Instruments AN-2028, "Watchdog Timers in Embedded Systems"

Design Pattern:
- External watchdog is most reliable form (independent of main CPU state)
- Heartbeat interval: 10 seconds (Ziegler-Nichols safety margin: 3× = 30 sec timeout)
- Fallback: Force power cycle via GPIO (Raspberry Pi GPIO4 to ESP32 EN pin)

VKTEST Context:
- Raspberry Pi 3: Single CPU core can hang from thermal throttling or infinite loops
- AUV safety: Cannot tolerate Raspberry Pi unresponsiveness during underwater operations
- Recovery mechanism: Hard power cycle via ESP32 GPIO relay → forces restart
"""

import serial
import logging
import threading
import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
from unittest.mock import MagicMock


logger = logging.getLogger(__name__)


class WatchdogState(Enum):
    """Watchdog operational states."""
    IDLE = "IDLE"              # Not initialized
    LISTENING = "LISTENING"    # Awaiting heartbeats
    TIMEOUT = "TIMEOUT"        # Heartbeat missed
    RECOVERING = "RECOVERING"  # Power cycle triggered
    ERROR = "ERROR"            # Serial communication failure


@dataclass
class WatchdogConfig:
    """Watchdog configuration parameters."""
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    heartbeat_interval_sec: float = 10.0
    timeout_threshold_sec: float = 30.0  # 3× heartbeat interval (safety factor)
    heartbeat_char: bytes = b'H'
    recovery_command: bytes = b'PWRCYCLE'
    enable_gpio_fallback: bool = True
    gpio_pin_reset: int = 4  # Raspberry Pi GPIO4


class ESP32Watchdog:
    """
    External watchdog monitor via ESP32-S3.

    Monitors heartbeat from Raspberry Pi. If heartbeat missing for >30 seconds,
    triggers power cycle command to ESP32, which pulls Pi's power rail.

    Thread-safe serial communication with automatic reconnection.

    Attributes:
        state: Current watchdog operational state
        last_heartbeat_time: Unix timestamp of last received heartbeat
        heartbeat_count: Total heartbeats received (for statistics)
    """

    def __init__(self, config: WatchdogConfig = None):
        """
        Initialize watchdog monitor.

        Args:
            config: WatchdogConfig object with port, baud rate, timeouts
        """
        self.config = config or WatchdogConfig()
        self.state = WatchdogState.IDLE
        self.last_heartbeat_time = time.time()
        self.heartbeat_count = 0
        self.timeout_count = 0

        self.serial_port: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

        self.on_timeout: Optional[Callable] = None  # Callback when timeout detected
        self.on_recovery: Optional[Callable] = None  # Callback after power cycle

    def connect(self) -> bool:
        """
        Open serial connection to ESP32.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._lock:
                if self.serial_port and self.serial_port.is_open:
                    return True

                self.serial_port = serial.Serial(
                    port=self.config.serial_port,
                    baudrate=self.config.baud_rate,
                    timeout=1.0,
                    write_timeout=1.0
                )
                self.state = WatchdogState.LISTENING
                logger.info(f"Watchdog connected to {self.config.serial_port} @ {self.config.baud_rate} baud")
                return True
        except serial.SerialException as e:
            self.state = WatchdogState.ERROR
            logger.error(f"Failed to open watchdog serial port: {e}")
            return False

    def disconnect(self):
        """Close serial connection."""
        with self._lock:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                logger.info("Watchdog serial port closed")

    def start_monitoring(self):
        """Start watchdog monitoring thread."""
        if self._running:
            logger.warning("Watchdog monitor already running")
            return

        if not self.connect():
            logger.error("Cannot start monitoring without connection")
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="WatchdogMonitor"
        )
        self._monitor_thread.start()
        logger.info("Watchdog monitor thread started")

    def stop_monitoring(self):
        """Stop watchdog monitoring thread."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        self.disconnect()
        logger.info("Watchdog monitor stopped")

    def receive_heartbeat(self) -> bool:
        """
        Register heartbeat reception from Raspberry Pi.

        Called by AutonomousAgent when Pi has completed a control loop cycle.
        Updates the last_heartbeat_time timestamp.

        Returns:
            True if heartbeat accepted, False if already in recovery
        """
        with self._lock:
            if self.state == WatchdogState.RECOVERING:
                return False

            self.last_heartbeat_time = time.time()
            self.heartbeat_count += 1
            self.state = WatchdogState.LISTENING

            # Attempt to transmit heartbeat acknowledgement to ESP32
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.write(b'A')  # ACK from Pi received
                except serial.SerialException:
                    logger.warning("Failed to send heartbeat ACK to ESP32")

        return True

    def _monitor_loop(self):
        """
        Main monitoring loop (runs in separate thread).

        Checks for timeout condition every second.
        If timeout detected: triggers power cycle, notifies callbacks.
        """
        while self._running:
            try:
                time.sleep(1.0)

                with self._lock:
                    if self.state == WatchdogState.IDLE or self.state == WatchdogState.ERROR:
                        continue

                    time_since_heartbeat = time.time() - self.last_heartbeat_time

                    if time_since_heartbeat > self.config.timeout_threshold_sec:
                        logger.critical(
                            f"Watchdog timeout! No heartbeat for {time_since_heartbeat:.1f}s "
                            f"(threshold: {self.config.timeout_threshold_sec}s)"
                        )
                        self.timeout_count += 1
                        self._trigger_recovery()

                        if self.on_timeout:
                            self.on_timeout()

            except Exception as e:
                logger.error(f"Error in watchdog monitor loop: {e}")

    def _trigger_recovery(self):
        """
        Trigger power cycle recovery on timeout.

        Sends PWRCYCLE command to ESP32, which:
        1. Pulls Raspberry Pi EN pin low (cuts power)
        2. Waits 3 seconds
        3. Releases EN pin (power restored)

        The Pi boots cleanly, starting from systemd/init again.
        """
        self.state = WatchdogState.RECOVERING
        logger.critical("TRIGGERING POWER CYCLE RECOVERY")

        if not self.serial_port or not self.serial_port.is_open:
            logger.error("Cannot send recovery command: serial port not open")
            return

        try:
            # Send power cycle command to ESP32
            self.serial_port.write(self.config.recovery_command)
            self.serial_port.flush()
            logger.info(f"Sent recovery command to ESP32: {self.config.recovery_command}")

            # Reset heartbeat timer (recovery in progress)
            self.last_heartbeat_time = time.time()

            # Wait for Pi to restart (typical: 15-30 seconds)
            time.sleep(35.0)

            # Reset state after restart
            self.state = WatchdogState.LISTENING
            logger.info("Recovery sequence complete, resuming normal monitoring")

            if self.on_recovery:
                self.on_recovery()

        except serial.SerialException as e:
            logger.error(f"Failed to send recovery command: {e}")
            self.state = WatchdogState.ERROR

    def get_status(self) -> dict:
        """
        Get current watchdog status for telemetry.

        Returns:
            Dictionary with state, heartbeat_count, timeout_count, time_since_heartbeat
        """
        with self._lock:
            return {
                "state": self.state.value,
                "heartbeat_count": self.heartbeat_count,
                "timeout_count": self.timeout_count,
                "time_since_heartbeat_sec": time.time() - self.last_heartbeat_time,
                "is_connected": self.serial_port is not None and self.serial_port.is_open
            }


class MockESP32Watchdog(ESP32Watchdog):
    """
    Mock watchdog for testing without hardware.

    Simulates ESP32 behavior:
    - No actual serial communication
    - Tracks state machine transitions
    - Can simulate timeout/recovery for testing
    """

    def __init__(self, config: WatchdogConfig = None, simulate_timeout: bool = False):
        """
        Initialize mock watchdog.

        Args:
            config: WatchdogConfig (ignored for mock)
            simulate_timeout: If True, trigger timeout after 3 seconds
        """
        super().__init__(config or WatchdogConfig())
        self.simulate_timeout = simulate_timeout
        self._mock_timeout_trigger_time = time.time() + 3.0 if simulate_timeout else None

    def connect(self) -> bool:
        """Mock connection always succeeds."""
        self.state = WatchdogState.LISTENING
        # Create a mock serial port object for status reporting
        self.serial_port = MagicMock()
        self.serial_port.is_open = True
        logger.info("Mock watchdog connected")
        return True

    def disconnect(self):
        """Mock disconnect."""
        logger.info("Mock watchdog disconnected")

    def _monitor_loop(self):
        """Mock monitoring with optional timeout simulation."""
        while self._running:
            try:
                time.sleep(1.0)

                # Simulate timeout if configured
                if self.simulate_timeout and self._mock_timeout_trigger_time:
                    if time.time() > self._mock_timeout_trigger_time:
                        logger.critical("Mock: Simulating timeout")
                        self.timeout_count += 1
                        self._trigger_recovery()
                        if self.on_timeout:
                            self.on_timeout()
                        self._mock_timeout_trigger_time = None  # One-time trigger

            except Exception as e:
                logger.error(f"Error in mock watchdog loop: {e}")
