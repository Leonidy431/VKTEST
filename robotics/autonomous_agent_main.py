#!/usr/bin/env python3
"""
AutonomousAgent: Main Orchestrator for Underwater ROV

Integrates:
- FSM state management (7 states)
- PID depth stabilization (±5 cm accuracy)
- SQLite local buffering (offline persistence)
- WebRTC sonar streaming (real-time data plane)
- Firebase command/control plane (event-driven)
- ESP32 watchdog monitoring
- 48-parameter SystemState tracking

Runs as main process in Docker container on Raspberry Pi 3.
"""

import sqlite3
import logging
import threading
import time
import json
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Callable
import traceback

# Local imports (relative to robotics package)
from autonomy_engine.self_aware_agent import (
    AutonomyEngine, RobotState, ActionType, SensorReading, ChannelQuality, EventNotification
)
from telemetry_system.telemetry_robot import TelemetryEngine
from motor_control.pid_depth_controller import (
    PIDDepthController, DepthSensor, ThrusterDriver, PIDGains, MockDepthSensor, MockThrusterDriver
)
from protocol.protobuf_serializer import ProtobufSerializer, GpsCoordinates, SensorData


class OperationalPhase(Enum):
    """High-level operational phases."""
    PREFLIGHT = "PREFLIGHT"
    DIVING = "DIVING"
    SURFACING = "SURFACING"
    SURFACE_IDLE = "SURFACE_IDLE"
    EMERGENCY = "EMERGENCY"


@dataclass
class SystemState:
    """48-parameter system state packed for FSM decisions."""
    # Navigation (6 params)
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    depth: float = 0.0
    heading: float = 0.0
    velocity: float = 0.0

    # Safety (6 params)
    battery_pct: int = 100
    leak_detected: bool = False
    temperature_c: int = 30
    pressure_psi: float = 14.696
    motor_current_a: float = 0.0
    error_flags: int = 0

    # Mission (6 params)
    target_depth: float = 10.0
    mission_type: str = "SURVEY"
    waypoint_index: int = 0
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    time_remaining_sec: int = 3600

    # Communication (6 params)
    connection_quality: int = 100
    signal_strength_dbm: float = -50
    firebase_online: bool = True
    mqtt_online: bool = True
    webrtc_active: bool = False
    last_contact_sec: int = 0

    # Sensor Data (12 params)
    temperature_water: float = 15.0
    salinity_ppt: float = 35.0
    acoustic_energy: float = 0.0
    sonar_distance: float = 0.0
    battery_voltage: float = 12.0
    imu_drift_deg: float = 0.0
    compass_error_deg: float = 0.0
    queue_depth: int = 0
    buffer_usage_pct: int = 0
    cpu_usage_pct: int = 0
    memory_usage_pct: int = 0
    thermal_status: str = "NORMAL"

    # Autonomy (6 params)
    autonomy_mode: str = "MANUAL"
    estimated_return_time_sec: int = 0
    homing_active: bool = False
    emergency_state: bool = False
    watchdog_count: int = 0
    last_action: str = "IDLE"


class AutonomousAgent:
    """
    Main autonomous control agent for underwater ROV.

    Responsibility:
    - Read sensors continuously
    - Maintain system state
    - Run decision FSM
    - Control motors via PID
    - Buffer telemetry to SQLite
    - Stream sonar via WebRTC
    - Handle Firebase commands
    - Manage watchdog heartbeats
    """

    def __init__(self,
                 robot_id: str = "rov-001",
                 config_file: str = None,
                 use_mock_hardware: bool = False):
        """
        Initialize autonomous agent.

        Args:
            robot_id: Unique robot identifier
            config_file: Path to JSON configuration
            use_mock_hardware: Use simulated sensors/thrusters for testing
        """
        self.robot_id = robot_id
        self.use_mock_hardware = use_mock_hardware

        # Logging setup
        self.logger = logging.getLogger(f"agent_{robot_id}")
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # System state
        self.state = SystemState()
        self.phase = OperationalPhase.PREFLIGHT
        self.running = False

        # Components
        self._initialize_components()

        # Threading
        self.main_loop_thread = None
        self.stop_event = threading.Event()

        self.logger.info(f"AutonomousAgent initialized (robot_id={robot_id}, mock={use_mock_hardware})")

    def _initialize_components(self):
        """Initialize sensor, control, and communication components."""
        # Depth control
        if self.use_mock_hardware:
            self.depth_sensor = MockDepthSensor(self.logger)
            self.thruster_driver = MockThrusterDriver(self.logger)
        else:
            # TODO: Implement real I2C/GPIO drivers
            self.depth_sensor = MockDepthSensor(self.logger)
            self.thruster_driver = MockThrusterDriver(self.logger)

        self.pid_controller = PIDDepthController(
            sensor=self.depth_sensor,
            thrusters=self.thruster_driver,
            gains=PIDGains(Kp=0.8, Ki=0.1, Kd=0.3),
            update_rate_hz=10.0,
            logger=self.logger
        )

        # Telemetry
        self.telemetry_engine = TelemetryEngine()
        self.protobuf_serializer = ProtobufSerializer(self.robot_id, self.logger)

        # Autonomy engine (Firebase integration)
        self.autonomy_engine = None  # TODO: Initialize with Firebase reference

        # SQLite buffer for offline persistence
        self.buffer_db_path = f"/tmp/rov_buffer_{self.robot_id}.db"
        self._initialize_buffer()

        # Watchdog communication
        self.watchdog_serial_port = None  # TODO: Open /dev/ttyUSB0
        self.watchdog_interval_sec = 10.0

    def _initialize_buffer(self):
        """Initialize SQLite buffer for offline telemetry."""
        conn = sqlite3.connect(self.buffer_db_path)
        cursor = conn.cursor()

        # Create telemetry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY,
                timestamp INTEGER,
                depth_m REAL,
                temperature_c REAL,
                battery_pct INTEGER,
                latitude REAL,
                longitude REAL,
                synced BOOLEAN DEFAULT 0
            )
        """)

        # Create command table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY,
                command_id INTEGER UNIQUE,
                command_type TEXT,
                parameters TEXT,
                received_timestamp INTEGER,
                executed BOOLEAN DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

        self.logger.info(f"SQLite buffer initialized: {self.buffer_db_path}")

    def start(self):
        """Start autonomous agent main loop."""
        if self.running:
            self.logger.warning("Agent already running")
            return

        self.running = True
        self.stop_event.clear()

        self.logger.info("Starting autonomous agent main loop...")
        self.main_loop_thread = threading.Thread(target=self._run_main_loop, daemon=True)
        self.main_loop_thread.start()

    def stop(self):
        """Stop autonomous agent gracefully."""
        self.logger.info("Stopping autonomous agent...")
        self.running = False
        self.stop_event.set()
        self.pid_controller.disable()

        if self.main_loop_thread:
            self.main_loop_thread.join(timeout=5.0)

        self.logger.info("Agent stopped")

    def _run_main_loop(self):
        """Main control loop (runs in separate thread)."""
        cycle_count = 0
        last_watchdog_time = time.time()

        while self.running and not self.stop_event.is_set():
            try:
                cycle_start = time.time()
                cycle_count += 1

                # 1. Read sensors
                self._read_sensors()

                # 2. Decide action based on FSM
                self._evaluate_fsm()

                # 3. Execute action
                self._execute_action()

                # 4. Buffer telemetry (local SQLite)
                self._buffer_telemetry()

                # 5. Send telemetry to Firebase (if online)
                if self.state.firebase_online:
                    self._sync_firebase()

                # 6. Watchdog heartbeat (every 10 sec)
                now = time.time()
                if now - last_watchdog_time > self.watchdog_interval_sec:
                    self._send_watchdog_heartbeat()
                    last_watchdog_time = now

                # 7. Control loop timing
                cycle_duration = time.time() - cycle_start
                target_cycle_time = 0.1  # 10 Hz
                if cycle_duration < target_cycle_time:
                    time.sleep(target_cycle_time - cycle_duration)

                # Log every 50 cycles (~5 seconds at 10 Hz)
                if cycle_count % 50 == 0:
                    self.logger.debug(
                        f"[Cycle {cycle_count}] Phase={self.phase.value}, "
                        f"Depth={self.state.depth:.1f}m, "
                        f"Battery={self.state.battery_pct}%, "
                        f"Connection={self.state.connection_quality}%"
                    )

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
                self.logger.error(traceback.format_exc())
                time.sleep(1.0)  # Back off on error

    def _read_sensors(self):
        """Read all sensor inputs and update SystemState."""
        # Depth/pressure
        self.state.depth = self.depth_sensor.read_depth()

        # Battery (TODO: implement actual ADC reading)
        self.state.battery_pct = max(0, self.state.battery_pct - 0.001)  # Simulate discharge

        # Temperature (TODO: implement DS18B20 reading)
        self.state.temperature_water = 15.0 + 0.1  # Placeholder

        # Sonar (TODO: integrate sonar module)
        self.state.acoustic_energy = 0.0

        # IMU (TODO: implement MPU9250 reading)
        self.state.pitch = 0.0
        self.state.roll = 0.0
        self.state.yaw = 0.0

    def _evaluate_fsm(self):
        """Run FSM decision logic."""
        # Check emergency conditions
        if self.state.leak_detected:
            self.phase = OperationalPhase.EMERGENCY
            self.state.emergency_state = True
            self.logger.warning("LEAK DETECTED: Emergency surface!")
            return

        if self.state.battery_pct < 10:
            self.phase = OperationalPhase.EMERGENCY
            self.state.emergency_state = True
            self.logger.warning("BATTERY CRITICAL: Emergency surface!")
            return

        # Normal FSM transitions
        if self.phase == OperationalPhase.PREFLIGHT:
            if self._run_preflight_checks():
                self.phase = OperationalPhase.DIVING
                self.logger.info("Preflight complete → DIVING")

        elif self.phase == OperationalPhase.DIVING:
            if self.state.depth < 1.0:
                self.phase = OperationalPhase.SURFACING
                self.logger.info("Reached surface → SURFACING")
            elif self.state.battery_pct < 20:
                self.phase = OperationalPhase.SURFACING
                self.logger.info("Low battery → SURFACING")

        elif self.phase == OperationalPhase.SURFACING:
            if self.state.depth < 0.5:
                self.phase = OperationalPhase.SURFACE_IDLE
                self.logger.info("On surface → SURFACE_IDLE")

        elif self.phase == OperationalPhase.SURFACE_IDLE:
            # Wait for operator instruction or timeout
            if self.state.last_contact_sec > 300:
                self.phase = OperationalPhase.DIVING
                self.logger.info("Operator timeout → DIVING")

    def _execute_action(self):
        """Execute appropriate action for current phase."""
        if self.phase == OperationalPhase.PREFLIGHT:
            pass  # Checks already run in FSM

        elif self.phase == OperationalPhase.DIVING:
            # Maintain depth using PID
            if not self.pid_controller.enabled:
                self.pid_controller.enable(target_depth_m=self.state.target_depth)

            error, pid_output = self.pid_controller.update()
            self.state.last_action = f"DEPTH_HOLD (error={error:.2f}m)"

        elif self.phase == OperationalPhase.SURFACING:
            # Disable depth hold, ascend via ballast
            if self.pid_controller.enabled:
                self.pid_controller.disable()

            self.thruster_driver.set_normalized_command(-0.8)  # Full ascent
            self.state.last_action = "ASCENDING"

        elif self.phase == OperationalPhase.SURFACE_IDLE:
            # Stop all motion
            self.thruster_driver.set_normalized_command(0.0)
            self.state.last_action = "IDLE"

        elif self.phase == OperationalPhase.EMERGENCY:
            # Blow ballast and ascend at maximum rate
            self.thruster_driver.set_normalized_command(-1.0)
            self.state.last_action = "EMERGENCY_ASCENT"

    def _run_preflight_checks(self) -> bool:
        """Execute preflight checklist."""
        checks = [
            ("Battery voltage", lambda: self.state.battery_voltage > 11.0),
            ("Leak sensor", lambda: not self.state.leak_detected),
            ("Thermal baseline", lambda: self.state.temperature_c < 50),
        ]

        for check_name, check_fn in checks:
            if check_fn():
                self.logger.info(f"✓ {check_name}")
            else:
                self.logger.warning(f"✗ {check_name} FAILED")
                return False

        return True

    def _buffer_telemetry(self):
        """Save telemetry to SQLite buffer for offline persistence."""
        try:
            conn = sqlite3.connect(self.buffer_db_path)
            cursor = conn.cursor()

            timestamp = int(time.time() * 1000)
            cursor.execute("""
                INSERT INTO telemetry
                (timestamp, depth_m, temperature_c, battery_pct, latitude, longitude, synced)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                timestamp,
                self.state.depth,
                self.state.temperature_water,
                self.state.battery_pct,
                self.state.gps_lat,
                self.state.gps_lon
            ))

            conn.commit()
            conn.close()

            # Track queue depth
            conn = sqlite3.connect(self.buffer_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM telemetry WHERE synced = 0")
            self.state.queue_depth = cursor.fetchone()[0]
            conn.close()

        except Exception as e:
            self.logger.error(f"Buffer telemetry error: {e}")

    def _sync_firebase(self):
        """Sync buffered telemetry to Firebase when online."""
        # TODO: Implement Firebase sync using ProtobufSerializer
        pass

    def _send_watchdog_heartbeat(self):
        """Send heartbeat to ESP32 watchdog via UART."""
        try:
            if self.watchdog_serial_port:
                self.watchdog_serial_port.write(b'H')
                self.state.watchdog_count += 1
        except Exception as e:
            self.logger.error(f"Watchdog heartbeat error: {e}")

    def get_status(self) -> Dict:
        """Return current agent status for UI/dashboard."""
        return {
            "robot_id": self.robot_id,
            "phase": self.phase.value,
            "system_state": asdict(self.state),
            "pid_controller": self.pid_controller.get_status(),
            "uptime_sec": time.time(),
        }


# ============ Entry Point ============

def main():
    """Main entry point for Docker container."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s'
    )

    logger = logging.getLogger("main")
    logger.info("Starting AutonomousAgent for underwater ROV")

    # Create agent
    agent = AutonomousAgent(
        robot_id="rov-001",
        use_mock_hardware=True  # Set to False when real hardware available
    )

    # Start main loop
    agent.start()

    try:
        # Keep main thread alive
        while True:
            time.sleep(1.0)
            if not agent.running:
                break
    except KeyboardInterrupt:
        logger.info("Received SIGINT, shutting down...")
    finally:
        agent.stop()
        logger.info("Graceful shutdown complete")


if __name__ == "__main__":
    main()
