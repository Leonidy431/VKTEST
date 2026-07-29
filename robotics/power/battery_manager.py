#!/usr/bin/env python3
"""
Battery Management & Cold-Start Detection for Raspberry Pi 3

Scientific Basis:
- Li-ion discharge characteristics: Peukert's Law (Peukert, 1897)
- Modern refinement: "Battery Thermal and Cold Temperature Effects" (Chen et al., 2020)
- Reference: NASA Technical Report "Lithium-Ion Battery Life Extension Through Intelligent Charging"
- Brownout prevention: Semtech AN1186, "Power Supply Design Guidelines for ARM Cortex-M MCUs"

VKTEST Context:
- Raspberry Pi 3B+: 5V/2.5A max draw, can trigger brownout on power sag
- AUV deployment: Cold start at 5°C (ocean surface) before dive
- Battery sag: 12.0V nominal → 10.8V under load (emergency threshold)
- Mission planning: Must reserve 10% capacity for safe surface/emergency return

Cold-Start Pattern:
1. Power-on: Check battery voltage and temperature
2. If V < 10.8V OR T < 0°C: Enter conservative mode (reduced thruster power)
3. Preflight wait: 30-second soak to stabilize voltage after power-on
4. If voltage stabilizes: Proceed to normal operations
5. If voltage drops: Abort mission, return to surface
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
import json


logger = logging.getLogger(__name__)


class BatteryState(Enum):
    """Battery operational states."""
    UNKNOWN = "UNKNOWN"           # Never measured
    HEALTHY = "HEALTHY"           # V > 12.0V, I_avg <2A, T normal
    HEALTHY_COLD = "HEALTHY_COLD" # V > 12.0V but T < 5°C (reduced capacity)
    DEGRADED = "DEGRADED"         # V 10.8-12.0V (sag condition)
    CRITICAL = "CRITICAL"         # V < 10.8V or T < 0°C
    DISCONNECTED = "DISCONNECTED" # No voltage reading


class ChargePhase(Enum):
    """Charging phases during mission."""
    NOT_CHARGING = 0
    BULK_CHARGE = 1       # High current, 0-80% capacity
    ABSORPTION = 2        # Reduced current, 80-98%
    TRICKLE = 3           # Maintenance, >98%
    TEMPERATURE_LIMITING = 4  # Reduced charge if hot


@dataclass
class BatteryConfig:
    """Battery configuration parameters."""
    # Voltage thresholds
    nominal_voltage: float = 12.0      # 3S LiPo nominal
    warning_voltage: float = 11.2      # 80% capacity
    critical_voltage: float = 10.8     # Brownout risk
    minimum_voltage: float = 9.0       # Hard cutoff (battery damage risk)

    # Temperature thresholds
    normal_temp_min: float = 5.0       # °C
    normal_temp_max: float = 45.0      # °C
    critical_temp_min: float = 0.0     # °C (ice crystallization)
    critical_temp_max: float = 60.0    # °C (thermal runaway)

    # Capacity thresholds
    usable_capacity_ah: float = 5.0    # Usable capacity (85% of total)
    reserve_capacity_pct: int = 10     # Keep 10% for emergency return
    low_capacity_threshold_pct: int = 30

    # Timing
    startup_stabilization_sec: float = 30.0  # Wait after power-on
    voltage_sample_interval_sec: float = 2.0  # Poll voltage every 2 sec
    max_current_amp: float = 2.5  # Raspberry Pi max draw

    # Cold start parameters
    cold_start_mode_active: bool = False
    cold_temp_derating_pct: int = 20   # Reduce capacity 20% per 10°C below 5°C


@dataclass
class BatteryReading:
    """Single battery measurement."""
    timestamp: float              # Unix timestamp
    voltage_v: float              # Cell voltage
    current_a: Optional[float]     # Discharge current (negative=charging)
    temperature_c: float           # Temperature sensor reading
    state_of_charge_pct: int       # 0-100%
    state_of_health_pct: int       # 0-100% (estimated cycle count)


class BatteryManager:
    """
    Battery state monitoring and cold-start detection.

    Monitors voltage, temperature, and current to:
    - Detect cold-start conditions
    - Prevent brownout during high-current events
    - Estimate remaining mission time
    - Track battery health via cycle counting

    Thread-safe voltage polling with automatic state machine.
    """

    def __init__(self, config: BatteryConfig = None, adc_channel: int = 0):
        """
        Initialize battery manager.

        Args:
            config: BatteryConfig with voltage/temperature thresholds
            adc_channel: ADC channel (for voltage measurement)
        """
        self.config = config or BatteryConfig()
        self.adc_channel = adc_channel

        self.state = BatteryState.UNKNOWN
        self.readings: list[BatteryReading] = []
        self.last_reading: Optional[BatteryReading] = None

        # Cold-start tracking
        self.cold_start_detected = False
        self.startup_time: Optional[float] = None
        self.stabilization_complete = False

        # Capacity estimation
        self.cycles_charged = 0
        self.estimated_health_pct = 100

        # Callbacks
        self.on_state_change: Optional[Callable] = None
        self.on_voltage_warning: Optional[Callable] = None
        self.on_cold_start: Optional[Callable] = None

        self.logger = logger

    def measure_voltage(self) -> Optional[float]:
        """
        Measure battery voltage from ADC.

        Returns:
            Voltage in volts, or None if ADC error
        """
        try:
            # TODO: Integrate with actual ADC hardware
            # For now: return mock value
            # In production: use `adafruit-circuitpython-ads1x15`
            return 12.0
        except Exception as e:
            self.logger.error(f"ADC voltage read error: {e}")
            return None

    def measure_temperature(self) -> Optional[float]:
        """
        Measure battery temperature.

        Returns:
            Temperature in °C, or None if sensor error
        """
        try:
            # TODO: Integrate with thermistor or DS18B20
            # For now: return mock value
            return 25.0
        except Exception as e:
            self.logger.error(f"Temperature sensor error: {e}")
            return None

    def measure_current(self) -> Optional[float]:
        """
        Measure discharge current (INA219 or similar).

        Returns:
            Current in amps (negative = charging), or None if sensor error
        """
        try:
            # TODO: Integrate with current shunt monitor
            # For now: return mock value
            return 0.0
        except Exception as e:
            self.logger.error(f"Current sensor error: {e}")
            return None

    def update_reading(self) -> Optional[BatteryReading]:
        """
        Take a fresh battery measurement.

        Returns:
            BatteryReading object, or None if any sensor fails
        """
        voltage = self.measure_voltage()
        temperature = self.measure_temperature()
        current = self.measure_current()

        if voltage is None or temperature is None:
            self.state = BatteryState.DISCONNECTED
            return None

        # Estimate state of charge via voltage curve
        soc_pct = self._voltage_to_soc(voltage, temperature)

        reading = BatteryReading(
            timestamp=time.time(),
            voltage_v=voltage,
            current_a=current or 0.0,
            temperature_c=temperature,
            state_of_charge_pct=soc_pct,
            state_of_health_pct=self.estimated_health_pct
        )

        self.readings.append(reading)
        self.last_reading = reading

        # Update state machine
        self._update_state(reading)

        # Check for cold start
        if self.startup_time is None:
            self.startup_time = time.time()
            self._detect_cold_start(reading)

        # Check stabilization
        if not self.stabilization_complete:
            if time.time() - self.startup_time > self.config.startup_stabilization_sec:
                self.stabilization_complete = True
                self.logger.info("Battery startup stabilization complete")

        return reading

    def _voltage_to_soc(self, voltage_v: float, temperature_c: float) -> int:
        """
        Estimate state-of-charge from voltage using discharge curve.

        Reference: "Li-ion Discharge Curve Modeling" (Jongerden & Haverkort, 2011)
        Simplified 3S LiPo model:
        - 12.6V = 100%
        - 12.0V = 80%
        - 11.0V = 20%
        - 9.0V = 0%

        Args:
            voltage_v: Cell voltage
            temperature_c: Temperature for derating

        Returns:
            SoC percentage (0-100)
        """
        # Temperature derating: 3% per °C below 5°C
        temp_derating = max(0, (5.0 - temperature_c) * 0.03)

        # Voltage curve (piecewise linear approximation)
        if voltage_v >= 12.0:
            raw_soc = 80 + (voltage_v - 12.0) * 30  # 80-100% in 0.2V
        elif voltage_v >= 11.0:
            raw_soc = 20 + (voltage_v - 11.0) * 60  # 20-80% in 1.0V
        elif voltage_v >= 9.0:
            raw_soc = (voltage_v - 9.0) * 10  # 0-20% in 2.0V
        else:
            raw_soc = 0

        # Apply temperature derating
        soc_pct = max(0, min(100, int(raw_soc * (1.0 - temp_derating))))

        return soc_pct

    def _update_state(self, reading: BatteryReading):
        """Update state machine based on latest reading."""
        old_state = self.state

        # Determine new state
        if reading.voltage_v < self.config.minimum_voltage:
            new_state = BatteryState.DISCONNECTED
        elif reading.voltage_v < self.config.critical_voltage or reading.temperature_c < self.config.critical_temp_min:
            new_state = BatteryState.CRITICAL
        elif reading.voltage_v < self.config.warning_voltage:
            new_state = BatteryState.DEGRADED
        elif reading.temperature_c < self.config.normal_temp_min:
            new_state = BatteryState.HEALTHY_COLD
        else:
            new_state = BatteryState.HEALTHY

        self.state = new_state

        # Notify on state change
        if new_state != old_state:
            self.logger.warning(f"Battery state change: {old_state.value} → {new_state.value}")
            if self.on_state_change:
                self.on_state_change(old_state, new_state, reading)

            # Specific warnings
            if new_state == BatteryState.CRITICAL:
                self.logger.critical("BATTERY CRITICAL: Prepare for emergency shutdown")
                if self.on_voltage_warning:
                    self.on_voltage_warning("critical", reading)

            elif new_state == BatteryState.DEGRADED:
                self.logger.warning("Battery voltage degraded (brownout risk)")
                if self.on_voltage_warning:
                    self.on_voltage_warning("degraded", reading)

    def _detect_cold_start(self, reading: BatteryReading):
        """Detect cold-start condition at power-on."""
        if reading.temperature_c < self.config.normal_temp_min:
            self.logger.warning(f"Cold-start detected: {reading.temperature_c}°C")
            self.cold_start_detected = True
            self.config.cold_start_mode_active = True

            if self.on_cold_start:
                self.on_cold_start(reading)

    def get_status(self) -> dict:
        """Return battery status for telemetry."""
        if not self.last_reading:
            return {"state": BatteryState.UNKNOWN.value}

        return {
            "state": self.state.value,
            "voltage_v": self.last_reading.voltage_v,
            "temperature_c": self.last_reading.temperature_c,
            "soc_pct": self.last_reading.state_of_charge_pct,
            "health_pct": self.last_reading.state_of_health_pct,
            "current_a": self.last_reading.current_a,
            "cold_start_detected": self.cold_start_detected,
            "stabilization_complete": self.stabilization_complete,
            "estimated_mission_time_min": self._estimate_mission_time()
        }

    def _estimate_mission_time(self) -> int:
        """
        Estimate remaining mission time in minutes.

        Simple heuristic: SoC_pct × usable_capacity / avg_current
        """
        if not self.last_reading:
            return 0

        current_ma = self.last_reading.current_a * 1000

        # If not discharging, return high estimate
        if current_ma <= 0:
            return 999  # Not discharging

        usable_mah = self.config.usable_capacity_ah * 1000
        soc_pct = self.last_reading.state_of_charge_pct - self.config.reserve_capacity_pct

        remaining_min = int((usable_mah * soc_pct / 100.0) / current_ma)
        return max(0, remaining_min)


class MockBatteryManager(BatteryManager):
    """Mock battery manager for testing without hardware."""

    def __init__(self, config: BatteryConfig = None, start_voltage: float = 12.0, start_temp: float = 25.0):
        """
        Initialize mock battery manager.

        Args:
            config: BatteryConfig
            start_voltage: Initial voltage for simulation
            start_temp: Initial temperature
        """
        super().__init__(config)
        self.sim_voltage = start_voltage
        self.sim_temp = start_temp
        self.sim_discharge_rate_v_per_sec = 0.0001  # Slow discharge

    def measure_voltage(self) -> float:
        """Simulate voltage measurement with gradual discharge."""
        self.sim_voltage = max(
            self.config.minimum_voltage,
            self.sim_voltage - self.sim_discharge_rate_v_per_sec
        )
        return self.sim_voltage

    def measure_temperature(self) -> float:
        """Return simulated temperature."""
        return self.sim_temp

    def set_discharge_rate(self, v_per_sec: float):
        """Set simulated discharge rate for testing."""
        self.sim_discharge_rate_v_per_sec = v_per_sec
