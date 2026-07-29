"""
Unit tests for Battery Management module.

Tests cover:
- Battery state transitions
- Cold-start detection
- Voltage-to-SoC conversion
- Temperature derating
- Mission time estimation
"""

import time
import pytest
import sys

sys.path.insert(0, '/home/user/VKTEST')

from robotics.power.battery_manager import (
    BatteryManager,
    MockBatteryManager,
    BatteryState,
    BatteryConfig,
    BatteryReading,
)


class TestBatteryConfig:
    """Test BatteryConfig parameters."""

    def test_default_config(self):
        """Default config should have safe values."""
        config = BatteryConfig()
        assert config.nominal_voltage == 12.0
        assert config.critical_voltage == 10.8
        assert config.startup_stabilization_sec == 30.0
        assert config.reserve_capacity_pct == 10

    def test_custom_config(self):
        """Should accept custom configuration."""
        config = BatteryConfig(
            nominal_voltage=13.2,
            critical_voltage=11.0,
            startup_stabilization_sec=60.0
        )
        assert config.nominal_voltage == 13.2
        assert config.critical_voltage == 11.0
        assert config.startup_stabilization_sec == 60.0


class TestBatteryStateTransitions:
    """Test state machine transitions."""

    def test_init_state_unknown(self):
        """Should start in UNKNOWN state."""
        bm = MockBatteryManager()
        assert bm.state == BatteryState.UNKNOWN

    def test_healthy_state(self):
        """Should transition to HEALTHY with normal voltage/temp."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=25.0)
        bm.update_reading()
        assert bm.state == BatteryState.HEALTHY

    def test_healthy_cold_state(self):
        """Should transition to HEALTHY_COLD when cold."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=0.0)
        bm.update_reading()
        assert bm.state == BatteryState.HEALTHY_COLD

    def test_degraded_state(self):
        """Should transition to DEGRADED with low voltage."""
        bm = MockBatteryManager(start_voltage=11.0, start_temp=25.0)
        bm.update_reading()
        assert bm.state == BatteryState.DEGRADED

    def test_critical_state_low_voltage(self):
        """Should transition to CRITICAL with critical voltage."""
        bm = MockBatteryManager(start_voltage=10.5, start_temp=25.0)
        bm.update_reading()
        assert bm.state == BatteryState.CRITICAL

    def test_critical_state_cold_temp(self):
        """Should transition to CRITICAL with cold temperature."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=-5.0)
        bm.update_reading()
        assert bm.state == BatteryState.CRITICAL

    def test_disconnected_state(self):
        """Should clamp voltage to minimum and go to CRITICAL or DISCONNECTED."""
        config = BatteryConfig(minimum_voltage=8.0, critical_voltage=9.0)
        bm = MockBatteryManager(config=config, start_voltage=7.0, start_temp=25.0)
        bm.update_reading()
        # Mock clamps to minimum_voltage, so voltage becomes 8.0, which is < critical
        assert bm.state in (BatteryState.CRITICAL, BatteryState.DISCONNECTED)


class TestColdStartDetection:
    """Test cold-start condition detection."""

    def test_cold_start_detected(self):
        """Should detect cold-start at low temperature."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=2.0)
        bm.update_reading()
        assert bm.cold_start_detected is True
        assert bm.config.cold_start_mode_active is True

    def test_normal_start(self):
        """Should not trigger cold-start at normal temperature."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=25.0)
        bm.update_reading()
        assert bm.cold_start_detected is False

    def test_cold_start_callback(self):
        """Should invoke callback on cold-start detection."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=2.0)
        callback_called = False
        reading_arg = None

        def on_cold_start(reading):
            nonlocal callback_called, reading_arg
            callback_called = True
            reading_arg = reading

        bm.on_cold_start = on_cold_start
        bm.update_reading()

        assert callback_called is True
        assert reading_arg is not None
        assert reading_arg.temperature_c == 2.0


class TestVoltageToSOC:
    """Test voltage-to-charge conversion."""

    def test_full_charge_voltage(self):
        """Full charge should be ~100% SOC."""
        bm = MockBatteryManager()
        soc = bm._voltage_to_soc(12.6, 25.0)
        assert soc >= 95  # Allow small margin

    def test_half_charge_voltage(self):
        """~11.0V should be ~20% SOC."""
        bm = MockBatteryManager()
        soc = bm._voltage_to_soc(11.0, 25.0)
        assert 10 <= soc <= 30

    def test_low_charge_voltage(self):
        """~9.0V should be 0% SOC."""
        bm = MockBatteryManager()
        soc = bm._voltage_to_soc(9.0, 25.0)
        assert soc <= 5

    def test_temperature_derating(self):
        """Cold temperature should reduce estimated SOC."""
        bm = MockBatteryManager()
        soc_warm = bm._voltage_to_soc(11.0, 25.0)
        soc_cold = bm._voltage_to_soc(11.0, 0.0)
        # Cold should estimate lower capacity
        assert soc_cold <= soc_warm


class TestStateChangeCallback:
    """Test state change notifications."""

    def test_state_change_callback_triggered(self):
        """Should invoke callback on state change."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=25.0)
        bm.update_reading()

        state_changes = []

        def on_state_change(old, new, reading):
            state_changes.append((old, new))

        bm.on_state_change = on_state_change

        # Simulate voltage drop
        bm.sim_voltage = 10.9
        bm.update_reading()

        assert len(state_changes) == 1
        assert state_changes[0][0] == BatteryState.HEALTHY
        assert state_changes[0][1] == BatteryState.DEGRADED

    def test_voltage_warning_callback(self):
        """Should invoke warning callback for critical voltage."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=25.0)
        bm.update_reading()

        warnings = []

        def on_warning(level, reading):
            warnings.append(level)

        bm.on_voltage_warning = on_warning

        # Drop to critical
        bm.sim_voltage = 10.5
        bm.update_reading()

        assert "critical" in warnings


class TestStabilizationTimeout:
    """Test startup stabilization timer."""

    def test_stabilization_completes(self):
        """Should mark stabilization complete after timeout."""
        bm = MockBatteryManager()
        bm.config.startup_stabilization_sec = 0.1  # Short timeout for testing

        assert bm.stabilization_complete is False
        bm.update_reading()
        assert bm.stabilization_complete is False

        time.sleep(0.2)
        bm.update_reading()
        assert bm.stabilization_complete is True


class TestMissionTimeEstimation:
    """Test remaining mission time calculation."""

    def test_mission_time_high_capacity(self):
        """Should estimate reasonable mission time with full battery."""
        bm = MockBatteryManager(start_voltage=12.6, start_temp=25.0)
        reading = bm.update_reading()
        # Mock high current draw
        reading.current_a = 1.0

        mission_time = bm._estimate_mission_time()
        assert mission_time > 0
        assert mission_time < 500  # Should be reasonable estimate

    def test_mission_time_low_capacity(self):
        """Should estimate less mission time with low SOC."""
        bm = MockBatteryManager(start_voltage=9.5, start_temp=25.0)
        reading = bm.update_reading()
        reading.current_a = 1.0

        mission_time = bm._estimate_mission_time()
        assert mission_time == 0  # Below reserve capacity

    def test_mission_time_no_discharge(self):
        """Should return high estimate when not discharging."""
        bm = MockBatteryManager()
        reading = bm.update_reading()
        # Set current to 0 (not discharging)
        reading.current_a = 0.0
        mission_time = bm._estimate_mission_time()
        assert mission_time == 999


class TestGetStatus:
    """Test status reporting."""

    def test_status_reporting(self):
        """Should return comprehensive status dict."""
        bm = MockBatteryManager(start_voltage=12.0, start_temp=25.0)
        bm.update_reading()

        status = bm.get_status()

        assert "state" in status
        assert status["state"] == BatteryState.HEALTHY.value
        assert "voltage_v" in status
        assert abs(status["voltage_v"] - 12.0) < 0.001  # Float comparison
        assert "temperature_c" in status
        assert "soc_pct" in status
        assert "health_pct" in status
        assert "cold_start_detected" in status
        assert "stabilization_complete" in status
        assert "estimated_mission_time_min" in status

    def test_status_unknown_no_reading(self):
        """Should handle status with no readings."""
        bm = MockBatteryManager()
        status = bm.get_status()
        assert status["state"] == BatteryState.UNKNOWN.value


class TestBatteryReading:
    """Test BatteryReading dataclass."""

    def test_battery_reading_creation(self):
        """Should create valid BatteryReading."""
        reading = BatteryReading(
            timestamp=time.time(),
            voltage_v=12.0,
            current_a=1.0,
            temperature_c=25.0,
            state_of_charge_pct=80,
            state_of_health_pct=95
        )

        assert reading.voltage_v == 12.0
        assert reading.state_of_charge_pct == 80
        assert reading.state_of_health_pct == 95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
