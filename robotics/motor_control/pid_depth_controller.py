"""
PID Depth Stabilization Controller for Autonomous Underwater Vehicle

Maintains depth within ±5 cm during sonar scanning.

Theory:
  error = target_depth - current_depth
  PID_output = Kp*error + Ki*∑error + Kd*d(error)/dt
  thruster_command = neutral_position + PID_output

Hardware Requirements:
  - Pressure sensor (I2C/analog): 0-300 m depth range
  - Vertical thrusters (2x): PWM servo control (1000-2000 µs)
  - IMU (optional): Roll/pitch compensation
"""

import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import math


class ThrusterMode(Enum):
    """Thruster control states."""
    IDLE = 0           # Neutral, no thrust
    ASCENDING = 1      # Reducing ballast / increasing buoyancy
    DESCENDING = 2     # Adding ballast / reducing buoyancy
    HOLDING = 3        # Maintaining depth (hovering)


@dataclass
class PIDGains:
    """PID tuning constants."""
    Kp: float = 0.8    # Proportional gain (0.5-2.0 typical)
    Ki: float = 0.1    # Integral gain (0.05-0.3 typical)
    Kd: float = 0.3    # Derivative gain (0.2-0.8 typical)

    # Anti-windup for integral term
    integral_max: float = 50.0     # Maximum accumulated error
    integral_min: float = -50.0    # Minimum accumulated error

    # Derivative smoothing (avoid noise sensitivity)
    derivative_filter_alpha: float = 0.7  # Low-pass filter coeff (0-1)


@dataclass
class DepthSensorCalibration:
    """Pressure sensor calibration parameters."""
    pressure_at_surface_psi: float = 14.696   # 1 atm at sea level
    water_density_kg_m3: float = 1025.0       # Saltwater (1000 = fresh)
    gravity_m_s2: float = 9.81

    def pressure_to_depth(self, pressure_psi: float) -> float:
        """Convert pressure (PSI) to depth (meters)."""
        pressure_pa = pressure_psi * 6894.76  # PSI to Pascals
        gauge_pressure = pressure_pa - (self.pressure_at_surface_psi * 6894.76)
        depth = gauge_pressure / (self.water_density_kg_m3 * self.gravity_m_s2)
        return max(0.0, depth)  # Clamp to surface

    def depth_to_pressure(self, depth_m: float) -> float:
        """Convert depth (meters) to pressure (PSI)."""
        gauge_pressure = depth_m * self.water_density_kg_m3 * self.gravity_m_s2
        pressure_pa = gauge_pressure + (self.pressure_at_surface_psi * 6894.76)
        pressure_psi = pressure_pa / 6894.76
        return pressure_psi


class DepthSensor:
    """Abstract pressure/depth sensor interface."""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.calibration = DepthSensorCalibration()
        self._last_pressure_psi = None
        self._pressure_filter_alpha = 0.8  # Low-pass filter

    def read_raw_pressure(self) -> float:
        """
        Read raw pressure from sensor (PSI).
        Implement in subclass for actual I2C/analog reading.
        """
        raise NotImplementedError("Subclass must implement read_raw_pressure()")

    def read_filtered_pressure(self) -> float:
        """Read pressure with low-pass filtering to reduce noise."""
        raw_psi = self.read_raw_pressure()

        if self._last_pressure_psi is None:
            self._last_pressure_psi = raw_psi
        else:
            # Exponential moving average
            self._last_pressure_psi = (
                self._pressure_filter_alpha * raw_psi +
                (1 - self._pressure_filter_alpha) * self._last_pressure_psi
            )

        return self._last_pressure_psi

    def read_depth(self) -> float:
        """Read depth in meters (filtered)."""
        pressure_psi = self.read_filtered_pressure()
        return self.calibration.pressure_to_depth(pressure_psi)


class MockDepthSensor(DepthSensor):
    """Simulated pressure sensor for testing."""

    def __init__(self, logger: logging.Logger = None):
        super().__init__(logger)
        self._simulated_depth = 0.0
        self._drift_per_sec = 0.0  # Simulated leak or buoyancy drift

    def read_raw_pressure(self) -> float:
        """Return simulated pressure (with optional drift)."""
        self._simulated_depth += self._drift_per_sec * (time.time() % 1.0)
        pressure_psi = self.calibration.depth_to_pressure(self._simulated_depth)
        return pressure_psi

    def set_simulated_depth(self, depth_m: float):
        """Set current depth for simulation."""
        self._simulated_depth = depth_m

    def set_drift(self, drift_m_per_sec: float):
        """Simulate buoyancy drift (positive = sinking, negative = rising)."""
        self._drift_per_sec = drift_m_per_sec


class ThrusterDriver:
    """Abstract thruster/motor control interface."""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.neutral_pwm_us = 1500  # µs (neutral servo position)
        self.min_pwm_us = 1000      # µs (full reverse/ascent)
        self.max_pwm_us = 2000      # µs (full forward/descent)

    def set_thruster_command(self, pwm_microseconds: int):
        """
        Send PWM command to vertical thrusters.
        Implement in subclass for actual GPIO/servo control.
        """
        raise NotImplementedError("Subclass must implement set_thruster_command()")

    def set_normalized_command(self, normalized: float):
        """
        Set thruster command using normalized value (-1.0 to +1.0).
        -1.0 = full ascent (min PWM)
        0.0 = neutral/hovering
        +1.0 = full descent (max PWM)
        """
        normalized = max(-1.0, min(1.0, normalized))  # Clamp
        pwm = int(self.neutral_pwm_us + normalized * (self.max_pwm_us - self.neutral_pwm_us) / 2)
        self.set_thruster_command(pwm)


class MockThrusterDriver(ThrusterDriver):
    """Simulated thruster for testing."""

    def __init__(self, logger: logging.Logger = None):
        super().__init__(logger)
        self._last_command_us = self.neutral_pwm_us

    def set_thruster_command(self, pwm_microseconds: int):
        """Store command for testing."""
        self._last_command_us = pwm_microseconds

    def get_last_command_normalized(self) -> float:
        """Get last command as normalized value."""
        delta = self._last_command_us - self.neutral_pwm_us
        return delta / ((self.max_pwm_us - self.neutral_pwm_us) / 2)


class PIDDepthController:
    """
    PID controller for depth stabilization.

    Maintains target depth by commanding vertical thrusters.
    """

    def __init__(self,
                 sensor: DepthSensor,
                 thrusters: ThrusterDriver,
                 gains: PIDGains = None,
                 update_rate_hz: float = 10.0,
                 logger: logging.Logger = None):
        """
        Initialize PID controller.

        Args:
            sensor: DepthSensor instance for reading current depth
            thrusters: ThrusterDriver instance for motor control
            gains: PIDGains tuning parameters
            update_rate_hz: Control loop frequency (Hz)
            logger: Logging instance
        """
        self.sensor = sensor
        self.thrusters = thrusters
        self.gains = gains or PIDGains()
        self.update_rate_hz = update_rate_hz
        self.update_interval_sec = 1.0 / update_rate_hz
        self.logger = logger or logging.getLogger(__name__)

        # State tracking
        self.target_depth_m = 0.0
        self.current_depth_m = 0.0
        self.enabled = False
        self.mode = ThrusterMode.IDLE

        # PID state
        self.integral_error = 0.0
        self.last_error = 0.0
        self.last_derivative = 0.0
        self.last_update_time = None

        # Statistics
        self.error_samples = []
        self.max_error_abs = 0.0
        self.steady_state_reached = False
        self.steady_state_time_sec = 0.0
        self.steady_state_threshold_m = 0.05  # ±5 cm

        self.logger.info(f"PID Depth Controller initialized (Kp={self.gains.Kp}, "
                        f"Ki={self.gains.Ki}, Kd={self.gains.Kd})")

    def enable(self, target_depth_m: float):
        """Enable controller and set target depth."""
        self.target_depth_m = target_depth_m
        self.enabled = True
        self.integral_error = 0.0
        self.last_error = 0.0
        self.last_derivative = 0.0
        self.last_update_time = time.time()
        self.steady_state_time_sec = 0.0
        self.logger.info(f"PID enabled: target_depth={target_depth_m:.2f} m")

    def disable(self):
        """Disable controller (return to neutral thrust)."""
        self.enabled = False
        self.thrusters.set_normalized_command(0.0)
        self.mode = ThrusterMode.IDLE
        self.logger.info("PID disabled")

    def update(self) -> Tuple[float, float]:
        """
        Run one PID update cycle.

        Returns:
            (error_m, pid_output)
        """
        if not self.enabled:
            return 0.0, 0.0

        # Read current depth
        self.current_depth_m = self.sensor.read_depth()

        # Calculate error
        error = self.target_depth_m - self.current_depth_m

        # Update timing
        now = time.time()
        if self.last_update_time is None:
            dt = self.update_interval_sec
        else:
            dt = now - self.last_update_time
        self.last_update_time = now

        # Proportional term
        p_term = self.gains.Kp * error

        # Integral term (with anti-windup)
        self.integral_error += error * dt
        self.integral_error = max(self.gains.integral_min,
                                  min(self.gains.integral_max, self.integral_error))
        i_term = self.gains.Ki * self.integral_error

        # Derivative term (with low-pass filtering)
        if dt > 0:
            raw_derivative = (error - self.last_error) / dt
            self.last_derivative = (
                self.gains.derivative_filter_alpha * raw_derivative +
                (1 - self.gains.derivative_filter_alpha) * self.last_derivative
            )
        d_term = self.gains.Kd * self.last_derivative

        # Calculate PID output
        pid_output = p_term + i_term + d_term

        # Clamp to thruster range (-1.0 to +1.0)
        pid_output = max(-1.0, min(1.0, pid_output))

        # Send command to thrusters
        self.thrusters.set_normalized_command(pid_output)

        # Update mode
        if abs(error) < 0.01:
            self.mode = ThrusterMode.HOLDING
        elif error > 0:
            self.mode = ThrusterMode.DESCENDING
        else:
            self.mode = ThrusterMode.ASCENDING

        # Track statistics
        self.last_error = error
        self.error_samples.append(error)
        if len(self.error_samples) > 100:  # Keep last 100 samples
            self.error_samples.pop(0)

        abs_error = abs(error)
        self.max_error_abs = max(self.max_error_abs, abs_error)

        # Check for steady state (error within ±5 cm for 3+ seconds)
        if abs_error < self.steady_state_threshold_m:
            self.steady_state_time_sec += dt
            if self.steady_state_time_sec > 3.0:
                self.steady_state_reached = True
        else:
            self.steady_state_time_sec = 0.0
            self.steady_state_reached = False

        # Logging (periodic)
        if len(self.error_samples) % 10 == 0:
            self.logger.debug(
                f"Depth: {self.current_depth_m:.2f}m (target {self.target_depth_m:.2f}m), "
                f"error: {error:+.2f}m, "
                f"PID: {pid_output:+.3f}, "
                f"mode: {self.mode.name}"
            )

        return error, pid_output

    def get_status(self) -> dict:
        """Return controller status for diagnostics."""
        return {
            "enabled": self.enabled,
            "target_depth_m": self.target_depth_m,
            "current_depth_m": self.current_depth_m,
            "error_m": self.target_depth_m - self.current_depth_m,
            "mode": self.mode.name,
            "steady_state": self.steady_state_reached,
            "max_error_abs_m": self.max_error_abs,
            "integral_error": self.integral_error,
            "derivative_filtered": self.last_derivative,
            "error_samples_last_10": self.error_samples[-10:] if self.error_samples else [],
        }

    def tune_auto(self, test_depth_m: float = 10.0, duration_sec: float = 30.0):
        """
        Auto-tuning procedure using Ziegler-Nichols method.

        Finds critical oscillation frequency and adjusts gains.
        WARNING: This will cause the robot to oscillate. Use in safe environment only.
        """
        self.logger.warning(f"Starting auto-tune at {test_depth_m}m for {duration_sec}s")

        # Start with zero gains
        self.gains.Kp = 0.1
        self.gains.Ki = 0.0
        self.gains.Kd = 0.0

        self.enable(test_depth_m)
        start_time = time.time()
        peak_times = []
        last_error_sign = None

        while time.time() - start_time < duration_sec:
            error, _ = self.update()

            # Detect zero crossings (oscillation peaks)
            error_sign = 1 if error > 0 else -1
            if last_error_sign is not None and error_sign != last_error_sign:
                peak_times.append(time.time())
            last_error_sign = error_sign

            time.sleep(self.update_interval_sec)

        # Calculate Ziegler-Nichols gains
        if len(peak_times) >= 2:
            oscillation_period = 2 * (peak_times[-1] - peak_times[0]) / len(peak_times)
            Ku = 2 * self.gains.Kp  # Critical gain
            Tu = oscillation_period  # Critical period

            # Ziegler-Nichols for moderate overshoot
            self.gains.Kp = 0.33 * Ku
            self.gains.Ki = 0.66 * Ku / Tu
            self.gains.Kd = 0.11 * Ku * Tu

            self.logger.info(
                f"Auto-tune complete: Kp={self.gains.Kp:.3f}, "
                f"Ki={self.gains.Ki:.3f}, Kd={self.gains.Kd:.3f}"
            )
        else:
            self.logger.warning("Auto-tune failed: insufficient oscillation detected")

        self.disable()


# ============ Example Usage ============

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    logger = logging.getLogger("depth_control")

    # Create mock sensor and thrusters
    sensor = MockDepthSensor(logger)
    thrusters = MockThrusterDriver(logger)

    # Create PID controller
    gains = PIDGains(Kp=0.8, Ki=0.1, Kd=0.3)
    controller = PIDDepthController(sensor, thrusters, gains, update_rate_hz=10.0, logger=logger)

    # Test 1: Simple depth hold
    logger.info("\n=== Test 1: Depth Hold at 10m ===")
    sensor.set_simulated_depth(0.0)
    controller.enable(target_depth_m=10.0)

    for i in range(50):
        error, pid_output = controller.update()
        sensor.set_simulated_depth(sensor._simulated_depth + pid_output * 0.05)
        time.sleep(0.1)

    status = controller.get_status()
    logger.info(f"Final status: {status}")

    # Test 2: Drift compensation
    logger.info("\n=== Test 2: Drift Compensation ===")
    sensor.set_simulated_depth(10.0)
    sensor.set_drift(0.05)  # 5 cm/sec leak
    controller.enable(target_depth_m=10.0)

    for i in range(30):
        error, pid_output = controller.update()
        sensor.set_simulated_depth(
            sensor._simulated_depth + sensor._drift_per_sec * 0.1 + pid_output * 0.05
        )
        time.sleep(0.1)

    logger.info(f"Final status: {controller.get_status()}")
    controller.disable()
