"""
Self-Aware Autonomy Engine for Autonomous ROV/AUV

Architecture: "Intelligent Agent" mode
- Robot does NOT wait for operator instructions
- Robot evaluates channel quality and battery state
- Robot degrades gracefully without human intervention
- Robot sends structured EVENT notifications (not data spam)

Addresses Blind Spots:
- "Admin as Bottleneck": Operator might be offline/busy
- "Administrative Spam": Too many Firebase writes exhaust quotas
- "Ложная связь" (False Link): Detects if connection is dead despite showing WiFi

Decision Tree:
    Is there an OPERATOR INSTRUCTION?
         ├─ YES → Execute operator command + report back
         └─ NO  → Evaluate autonomous mode
                    ├─ Battery > 30%?
                    │   ├─ YES → Check channel quality
                    │   │   ├─ Good (>60%) → Send status report to admin
                    │   │   ├─ Degraded (10-60%) → Reduce telemetry rate, wait
                    │   │   └─ Lost (<10%) → AUTONOMOUS_MISSION
                    │   └─ NO → Execute RETURN_HOME + LOW_POWER_MODE
                    └─ No data received (offline) → AUTONOMOUS_MISSION (homing)
"""

import logging
import time
import json
from enum import Enum
from typing import Dict, Optional, Callable
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod


class RobotState(Enum):
    """High-level robot operational state."""
    DIVING_AUTONOMOUS = "diving_autonomous"      # Under water, no connection
    DIVING_CONNECTED = "diving_connected"        # Under water, connected to operator
    SURFACING = "surfacing"                      # Rising to surface
    SURFACE_IDLE = "surface_idle"                # On surface, waiting for instructions
    EXECUTING_COMMAND = "executing_command"      # Following operator instruction
    RETURNING_HOME = "returning_home"            # Autonomous return (battery low or lost)
    ERROR_SHUTDOWN = "error_shutdown"            # Critical failure, power down


class ActionType(Enum):
    """Type of action robot can take."""
    SEND_STATUS_REPORT = "send_status_report"    # Notify admin of status
    EXECUTE_OPERATOR_CMD = "execute_operator_cmd"  # Follow admin instruction
    AUTONOMOUS_MISSION = "autonomous_mission"    # Execute pre-programmed behavior
    REDUCE_TELEMETRY = "reduce_telemetry"        # Decrease data transmission rate
    ENTER_SLEEP_MODE = "enter_sleep_mode"        # Low power state
    EMERGENCY_SHUTDOWN = "emergency_shutdown"    # Critical power down


@dataclass
class SensorReading:
    """Current robot sensor state."""
    timestamp: float
    depth_m: float
    battery_pct: int
    temperature_c: float
    lat: float
    lon: float
    device_id: str = "rov-001"
    error_flags: int = 0  # Bitfield for errors


@dataclass
class ChannelQuality:
    """Network connection quality metrics."""
    is_connected: bool
    signal_strength_dbm: float  # -120 (worst) to 0 (best)
    latency_ms: float
    packet_loss_pct: float
    estimated_bandwidth_kbps: float

    def get_quality_percent(self) -> int:
        """Calculate overall quality (0-100%)."""
        if not self.is_connected:
            return 0

        # Composite: signal (40%) + latency (30%) + packet_loss (30%)
        signal_score = max(0, min(100, (self.signal_strength_dbm + 120) * 100 / 120))
        latency_score = max(0, 100 - (self.latency_ms / 10))  # Degrade at 1s
        loss_score = max(0, 100 - (self.packet_loss_pct * 2))  # 50% = 0 score

        quality = (signal_score * 0.4 + latency_score * 0.3 + loss_score * 0.3)
        return int(quality)


@dataclass
class OperatorInstruction:
    """Instruction from remote operator."""
    command_id: str
    instruction: str  # "dive_to_depth:50", "return_home", "scan_area"
    parameters: Dict = None
    timestamp: float = None
    priority: int = 1  # 1 = high, 5 = low


class EventNotification:
    """Structured notification to send to admin."""

    TEMPLATE = {
        "event_type": None,      # "STATE_CHANGE", "CRITICAL_ALERT", "TASK_COMPLETE"
        "timestamp": None,
        "robot_id": "rov-001",
        "state": None,           # Current robot state
        "data": None,            # Minimal data (GPS, battery, depth)
        "action_taken": None     # What robot decided to do
    }

    def __init__(self, event_type: str, robot_state: RobotState, data: Dict):
        self.data = self.TEMPLATE.copy()
        self.data["event_type"] = event_type
        self.data["timestamp"] = time.time()
        self.data["state"] = robot_state.value
        self.data["data"] = data

    def to_json(self) -> str:
        """Serialize to JSON for Firebase."""
        return json.dumps(self.data, default=str)


class AutonomyEngine(ABC):
    """Base class for autonomy decision-making."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.robot_state = RobotState.DIVING_AUTONOMOUS
        self.last_operator_contact = 0
        self.operator_timeout_s = 300  # 5 minutes
        self.min_battery_for_mission = 30  # % (below this → return home)

    @abstractmethod
    def check_for_instructions(self) -> Optional[OperatorInstruction]:
        """Poll for operator instructions (from Firebase, etc)."""
        pass

    @abstractmethod
    def execute_action(self, action: ActionType, params: Dict):
        """Execute decided action."""
        pass

    @abstractmethod
    def send_notification(self, notification: EventNotification):
        """Send structured event to admin (Firebase, FCM)."""
        pass

    def evaluate_decision(self,
                         sensors: SensorReading,
                         channel: ChannelQuality) -> ActionType:
        """
        Main decision logic: evaluate robot state and decide action.

        Returns: ActionType (what robot should do next)
        """

        # 1. Check for operator instructions
        instruction = self.check_for_instructions()
        if instruction:
            self.last_operator_contact = time.time()
            return ActionType.EXECUTE_OPERATOR_CMD

        # 2. Evaluate battery critical level
        if sensors.battery_pct < 20:
            self.logger.warning(f"Battery critical: {sensors.battery_pct}%")
            self.robot_state = RobotState.RETURNING_HOME
            return ActionType.AUTONOMOUS_MISSION  # Return home

        # 3. Evaluate channel quality
        quality = channel.get_quality_percent()

        if quality > 60:
            # Good connection: maintain status reports
            if self.robot_state in [RobotState.DIVING_AUTONOMOUS, RobotState.DIVING_CONNECTED]:
                self.robot_state = RobotState.DIVING_CONNECTED
                return ActionType.SEND_STATUS_REPORT

            elif self.robot_state == RobotState.SURFACE_IDLE:
                return ActionType.SEND_STATUS_REPORT  # Wait for instructions

        elif quality > 10:
            # Degraded connection: reduce telemetry rate
            self.robot_state = RobotState.DIVING_AUTONOMOUS
            return ActionType.REDUCE_TELEMETRY

        else:
            # No connection: autonomous mode
            self.robot_state = RobotState.DIVING_AUTONOMOUS
            return ActionType.AUTONOMOUS_MISSION

        # 4. Operator timeout: if no instructions for 5 min despite connection
        time_since_contact = time.time() - self.last_operator_contact
        if (self.robot_state == RobotState.SURFACE_IDLE and
                time_since_contact > self.operator_timeout_s):
            self.logger.warning(
                f"Operator timeout: {time_since_contact:.0f}s, "
                "switching to autonomous"
            )
            return ActionType.AUTONOMOUS_MISSION

        # Default: continue current mission
        return ActionType.AUTONOMOUS_MISSION

    def run_main_loop(self,
                      sensor_reader: Callable[[], SensorReading],
                      channel_monitor: Callable[[], ChannelQuality]):
        """Main control loop: read sensors, decide, execute."""

        while True:
            try:
                # Read current state
                sensors = sensor_reader()
                channel = channel_monitor()

                # Decide action
                action = self.evaluate_decision(sensors, channel)

                # Log decision
                self.logger.info(
                    f"State={self.robot_state.value}, "
                    f"Battery={sensors.battery_pct}%, "
                    f"Channel={channel.get_quality_percent()}%, "
                    f"Action={action.value}"
                )

                # Execute action
                self.execute_action(action, {
                    "sensors": asdict(sensors),
                    "channel": asdict(channel)
                })

                # Send notification if state changed
                if action in [ActionType.SEND_STATUS_REPORT,
                             ActionType.AUTONOMOUS_MISSION]:
                    notify = EventNotification(
                        event_type="STATE_UPDATE",
                        robot_state=self.robot_state,
                        data={
                            "lat": sensors.lat,
                            "lon": sensors.lon,
                            "depth_m": sensors.depth_m,
                            "battery_pct": sensors.battery_pct,
                            "channel_quality": channel.get_quality_percent(),
                            "action": action.value
                        }
                    )
                    self.send_notification(notify)

                # Control loop rate
                time.sleep(5)  # Update every 5 seconds

            except Exception as e:
                self.logger.error(f"Autonomy loop error: {e}")
                time.sleep(10)  # Back off on error


class LocalAutonomyEngine(AutonomyEngine):
    """Local implementation for testing (no Firebase)."""

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self.pending_instructions = []

    def check_for_instructions(self) -> Optional[OperatorInstruction]:
        """Simulated instruction polling."""
        if self.pending_instructions:
            return self.pending_instructions.pop(0)
        return None

    def execute_action(self, action: ActionType, params: Dict):
        """Simulated action execution."""
        self.logger.info(f"Executing action: {action.value}")
        self.logger.debug(f"  Params: {params}")

    def send_notification(self, notification: EventNotification):
        """Log notification instead of sending."""
        self.logger.info(f"Notification: {notification.to_json()}")


class FirebaseAutonomyEngine(AutonomyEngine):
    """Firebase-integrated autonomy engine (production)."""

    def __init__(self, logger: logging.Logger, db_ref=None):
        super().__init__(logger)
        self.db_ref = db_ref  # Firebase reference

    def check_for_instructions(self) -> Optional[OperatorInstruction]:
        """Poll Firebase for operator commands."""
        if not self.db_ref:
            return None

        try:
            cmd_data = self.db_ref.child("commands").child("pending").get().val()

            if cmd_data:
                instr = OperatorInstruction(
                    command_id=cmd_data.get("id"),
                    instruction=cmd_data.get("cmd"),
                    parameters=cmd_data.get("params"),
                    timestamp=cmd_data.get("ts")
                )

                # Remove from queue
                self.db_ref.child("commands").child("pending").remove()

                return instr

        except Exception as e:
            self.logger.error(f"Command polling error: {e}")

        return None

    def execute_action(self, action: ActionType, params: Dict):
        """Execute action and log to Firebase."""
        self.logger.info(f"Firebase executing: {action.value}")

        if self.db_ref:
            try:
                self.db_ref.child("robot").child("last_action").set({
                    "action": action.value,
                    "timestamp": time.time(),
                    "params": params
                })
            except Exception as e:
                self.logger.error(f"Action log error: {e}")

    def send_notification(self, notification: EventNotification):
        """Send event notification via Firebase."""
        if self.db_ref:
            try:
                self.db_ref.child("admin_notifications").push(notification.data)
                self.logger.debug("Notification sent to Firebase")
            except Exception as e:
                self.logger.error(f"Notification send error: {e}")


# ============ Example Usage ============

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    logger = logging.getLogger("autonomy")

    engine = LocalAutonomyEngine(logger)

    # Simulate sensor readings
    def mock_sensor_reader():
        return SensorReading(
            timestamp=time.time(),
            depth_m=15.5,
            battery_pct=85,
            temperature_c=12.0,
            lat=34.9821,
            lon=33.9512
        )

    # Simulate channel quality
    def mock_channel_monitor():
        return ChannelQuality(
            is_connected=True,
            signal_strength_dbm=-75,
            latency_ms=150,
            packet_loss_pct=5,
            estimated_bandwidth_kbps=50
        )

    # Run autonomy loop for 30 seconds
    logger.info("Starting autonomy engine...")

    try:
        for i in range(6):
            sensors = mock_sensor_reader()
            channel = mock_channel_monitor()

            action = engine.evaluate_decision(sensors, channel)
            engine.logger.info(f"Decision #{i+1}: {action.value}")

            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("Autonomy engine stopped")
