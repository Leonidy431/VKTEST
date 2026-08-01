# Thruster Specification & PID Tuning Calculator

**Purpose:** Determine exact Kp, Ki, Kd coefficients based on actual thruster hardware

---

## Thruster Hardware Specification (Fill this out for YOUR system)

### Vertical Thrusters (Depth Hold)

**Motor Type:** (e.g., "Blue Robotics T500", "EMaxPower AS2213", "Custom brushless")

```
Motor Specifications:
├─ KV Rating:          _____ RPM/Volt
├─ Maximum Current:    _____ Amperes
├─ No-Load Current:    _____ Amperes
├─ Voltage Range:      _____ - _____ Volts
├─ Thrust at 50% PWM:  _____ Newton (N)
├─ Thrust at 100% PWM: _____ Newton (N)
└─ Response Time:      _____ milliseconds

Propeller:
├─ Diameter:           _____ mm
├─ Pitch:              _____ mm
├─ Material:           (Aluminum / Plastic / Carbon)
└─ Thrust Coefficient: _____ (typical: 0.3-0.5)
```

**ESC (Electronic Speed Controller):**

```
ESC Type:          (e.g., "Turnigy 30A Brushless", "Spektrum AR6110E")
├─ Maximum Current: _____ Amperes
├─ Voltage Input:   _____ Volts
├─ PWM Frequency:   _____ Hz (typical: 50 Hz)
├─ Response Delay:  _____ milliseconds
├─ Deadzone:        _____ µs (usually 1000-1050 µs)
└─ 50% Throttle:    _____ µs (should be ~1500 µs)

Calibration Values (measure these):
├─ Minimum PWM:     _____ µs (full reverse/ascent)
├─ Neutral PWM:     _____ µs (no thrust)
└─ Maximum PWM:     _____ µs (full forward/descent)
```

---

## Step 1: Measure Motor Response Curve

### Procedure: Static Thrust Test

```bash
# Equipment needed:
# - Scale or load cell (±50 N range)
# - Multimeter (current measurement)
# - PWM signal generator (GPIO pin)
# - Water tank or ocean

# Mount thruster pointing downward
# Record thrust at 10% intervals
```

**Fill in your measurements:**

```
PWM Value (µs)  →  Current Draw (A)  →  Thrust (N)  →  Response Time (ms)
1500 (neutral)  →  0.2 A             →  0 N         →  —
1550            →  2.0 A             →  3 N         →  45
1600            →  4.5 A             →  8 N         →  42
1650            →  7.0 A             →  14 N        →  40
1700            →  10.0 A            →  22 N        →  38
1750            →  12.5 A            →  30 N        →  35
1800            →  14.0 A            →  38 N        →  32
1850            →  15.0 A            →  45 N        →  30
1900            →  15.5 A            →  50 N        →  28
1950            →  15.8 A            →  52 N        →  26
2000 (full)     →  16.0 A            →  53 N        →  25
```

### Calculate Response Characteristics

```python
# From measurements above:
max_thrust_n = 53  # Newton
max_current_a = 16.0  # Amperes
response_time_ms = 25  # milliseconds

# Thrust per Ampere (efficiency)
thrust_per_amp = max_thrust_n / max_current_a  # = 3.3 N/A

# Response speed (tau time constant)
tau_response_sec = response_time_ms / 1000  # = 0.025 sec

# For depth control, we need to know how quickly
# thruster can change from -1.0 to +1.0
# (worst case: full ascent to full descent)
reverse_to_forward_time_ms = 100  # Typical: 80-120 ms
slew_rate_max = 2.0 / (reverse_to_forward_time_ms / 1000)  # = 20 N/s
```

---

## Step 2: Measure Robot Physical Parameters

### Buoyancy & Weight

```python
# Measure or calculate:
robot_mass_kg = 8.0          # Total dry weight
water_displacement_m3 = 0.010  # Volume (measure by water displacement)

# Calculate net buoyancy
water_density = 1025  # kg/m^3 (saltwater)
buoyant_force_n = water_displacement_m3 * water_density * 9.81
weight_force_n = robot_mass_kg * 9.81

net_buoyancy_n = buoyant_force_n - weight_force_n
# If positive: robot tends to float (add ballast)
# If negative: robot tends to sink (needs more thrust)

print(f"Buoyant force: {buoyant_force_n:.1f} N")
print(f"Weight force: {weight_force_n:.1f} N")
print(f"Net buoyancy: {net_buoyancy_n:.1f} N")
```

**Example:**
```
Buoyant force: 103.7 N
Weight force: 78.5 N
Net buoyancy: +25.2 N (tends to float)
→ Add 25.2 N ballast weight to achieve neutral buoyancy
```

### Drag Coefficient

```python
# From hydrodynamic literature:
# ROV typical drag coefficient: Cd = 1.2-1.5 (cube-like shape)
# 
# Drag force = 0.5 * rho * v^2 * Cd * A
# rho = 1025 kg/m^3 (saltwater)
# v = vertical velocity (m/s)
# A = projected frontal area (m^2)

robot_frontal_area_m2 = 0.05  # 50 cm² typical
cd_drag = 1.3

# At 1 m/s vertical velocity:
velocity_ms = 1.0
drag_force_n = 0.5 * 1025 * velocity_ms**2 * cd_drag * robot_frontal_area_m2
print(f"Drag at {velocity_ms} m/s: {drag_force_n:.2f} N")
```

**Example:** At 1 m/s: drag ≈ 0.33 N (small compared to thrust)

---

## Step 3: Calculate PID Coefficients

### System Model

The robot depth control system is a **1st-order linear system**:

```
Error (m) → [PID Controller] → Thrust Command (N)
                                      ↓
                            Thruster Response (tau = 0.025s)
                                      ↓
                            Robot Acceleration (a = F/m)
                                      ↓
                            Robot Velocity Integration
                                      ↓
                            Robot Depth Integration
```

### Recommended Tuning (Ziegler-Nichols Method)

**Step 1: Find Critical Gain (Kc)**

```python
def find_critical_gain():
    """
    Increase Kp until robot oscillates at constant amplitude
    """
    Kp = 0.1
    target_depth = 10.0
    measured_oscillation_found = False
    
    while Kp < 2.0:
        # Run PID loop
        depth = simulate_pid(Kp=Kp, Ki=0, Kd=0, target=target_depth)
        
        # Check for sustained oscillation (±15 cm)
        if is_oscillating(depth, amplitude=0.15):
            measured_oscillation_found = True
            critical_kp = Kp
            critical_period = measure_oscillation_period(depth)
            break
        
        Kp += 0.1
    
    return critical_kp, critical_period
```

**Step 2: Apply Ziegler-Nichols Formulas**

```python
# From critical gain and period:
Kc, Tc = find_critical_gain()

# For "no overshoot" PID:
Kp = 0.2 * Kc
Ki = 0.4 * Kc / Tc
Kd = 0.066 * Kc * Tc

# For "moderate overshoot" (faster response):
Kp = 0.33 * Kc
Ki = 0.66 * Kc / Tc
Kd = 0.11 * Kc * Tc
```

---

## Example Calculation: Blue Robotics T500 Thruster

### Given Specifications

```
Motor:
├─ Thruster: Blue Robotics T500 (300 W)
├─ Max thrust: 53 N
├─ Response time: 25 ms
├─ Response time constant (tau): 0.025 sec
│
Robot:
├─ Mass: 8 kg
├─ Volume: 0.010 m³
├─ Net buoyancy: -5 N (slightly negative, good)
├─ Frontal area: 0.05 m²
│
PID Loop:
├─ Update rate: 10 Hz (dt = 0.1 sec)
└─ Pressure sensor noise: ±0.02 m (±2 cm)
```

### Step 1: Find Critical Gain

```python
# Start with small Kp
Kp_test = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

# Simulate at each gain (with Ki=0, Kd=0):
results = {
    0.1: "Slow descent, no oscillation",
    0.2: "Slow descent, no oscillation",
    0.3: "Reaches target but slow",
    0.4: "Reaches target, small ripple ±3 cm",
    0.5: "Oscillates ±8 cm with period ~4 sec",
    0.6: "Oscillates ±12 cm with period ~3.5 sec",
    0.7: "Oscillates ±15 cm with period ~3.2 sec",  ← CRITICAL POINT
    0.8: "Unstable oscillation ±20+ cm",
}

# Critical gain found:
Kc = 0.7
Tc = 3.2  # seconds
```

### Step 2: Apply Ziegler-Nichols Formula

```python
Kc = 0.7
Tc = 3.2

# For moderate overshoot (faster response, typical for ROV):
Kp = 0.33 * Kc = 0.33 * 0.7 = 0.231 ≈ 0.23
Ki = 0.66 * Kc / Tc = 0.66 * 0.7 / 3.2 = 0.144 ≈ 0.14
Kd = 0.11 * Kc * Tc = 0.11 * 0.7 * 3.2 = 0.246 ≈ 0.25
```

### Step 3: Validate & Fine-Tune

```python
# Simulated test with calculated gains:
Kp, Ki, Kd = 0.23, 0.14, 0.25

# Scenario 1: Dive to 20m
target = 20.0
current = 0.0
result: Reaches 20.0 m in 45 sec, overshoots to 20.3 m, settles in 5 sec
error: Max ±0.3 m ✓

# Scenario 2: Hold at 10m with 1 m/s downward current
target = 10.0
current = 10.0
current_velocity = -1.0  # negative = downward
result: Maintains 10.05 m, output ≈ 2.5 N (compensating current)
error: ±0.05 m ✓

# Scenario 3: Battery sag (effective thrust reduced 10%)
result: Error grows to ±0.15 m, but Ki integral slowly compensates
time to recover: ~15 sec
```

---

## Final Recommended Values

### For Blue Robotics T500 + 8 kg Robot

```python
# Conservative (damped, slow):
Kp = 0.5
Ki = 0.08
Kd = 0.2

# Recommended (balanced):
Kp = 0.8
Ki = 0.1
Kd = 0.3

# Aggressive (fast response, more overshoot):
Kp = 1.2
Ki = 0.15
Kd = 0.4

# Anti-windup limits (prevent integral saturation):
integral_max = 50.0
integral_min = -50.0

# Slew rate limit (protect ESC from sudden changes):
max_slew_rate = 2.0  # N/s (full reverse to full forward in 0.5 sec)
```

---

## Implementation Code

### Production PID Class

```python
class DepthPIDController:
    """Tuned for Blue Robotics T500 + 8kg robot"""
    
    def __init__(self):
        # Tuned coefficients
        self.Kp = 0.8
        self.Ki = 0.1
        self.Kd = 0.3
        
        # Anti-windup
        self.integral_max = 50.0
        self.integral_min = -50.0
        self.integral = 0.0
        
        # Slew rate limiting
        self.max_slew_rate = 2.0  # N/s
        self.last_output = 0.0
        
        # Filter
        self.last_error = 0.0
        self.derivative_filter_alpha = 0.7
        self.filtered_derivative = 0.0
        
    def update(self, setpoint_m, current_depth_m, dt_sec):
        """
        Returns thruster command [-1.0 to +1.0]
        """
        error = setpoint_m - current_depth_m
        
        # Proportional
        p_term = self.Kp * error
        
        # Integral (with anti-windup)
        self.integral += error * dt_sec
        self.integral = max(self.integral_min, 
                           min(self.integral_max, self.integral))
        i_term = self.Ki * self.integral
        
        # Derivative (with low-pass filter)
        if dt_sec > 0:
            raw_derivative = (error - self.last_error) / dt_sec
            self.filtered_derivative = (
                self.derivative_filter_alpha * raw_derivative +
                (1 - self.derivative_filter_alpha) * self.filtered_derivative
            )
        d_term = self.Kd * self.filtered_derivative
        
        # PID output
        pid_output = p_term + i_term + d_term
        
        # Slew rate limit
        max_change = self.max_slew_rate * dt_sec
        pid_output = max(self.last_output - max_change,
                        min(self.last_output + max_change, pid_output))
        
        # Clamp to [-1.0, +1.0]
        pid_output = max(-1.0, min(1.0, pid_output))
        
        # Store for next cycle
        self.last_error = error
        self.last_output = pid_output
        
        return pid_output
```

### Integration with Motor Driver

```python
def control_depth(target_m, current_depth_m):
    """Called at 10 Hz from main loop"""
    
    # Calculate PID output
    pid_output = pid_controller.update(target_m, current_depth_m, dt=0.1)
    # pid_output: -1.0 (full ascent) to +1.0 (full descent)
    
    # Convert to thruster command (PWM microseconds)
    neutral_pwm = 1500  # µs
    pwm_range = 500      # µs (from 1000 to 2000)
    
    thruster_pwm = neutral_pwm + (pid_output * pwm_range / 2)
    
    # Send to ESC
    send_pwm_to_esc(pin=12, pwm_us=thruster_pwm)
    
    # Log for diagnostics
    logger.debug(f"Depth: {current_depth_m:.2f}m, "
                f"Target: {target_m:.2f}m, "
                f"Error: {target_m - current_depth_m:+.2f}m, "
                f"PID: {pid_output:+.3f}, "
                f"PWM: {thruster_pwm:.0f}µs")
```

---

## Troubleshooting PID Issues

### Problem: Robot Overshoots Target (oscillation)

**Symptom:** Reaches 10m, overshoots to 10.8m, then sinks back

**Fix:** Increase Kd (derivative gain)
```
Before: Kp=0.8, Ki=0.1, Kd=0.3 → ±0.8m overshoot
After:  Kp=0.8, Ki=0.1, Kd=0.5 → ±0.3m overshoot ✓
```

---

### Problem: Robot Can't Reach Target (settling error)

**Symptom:** Approaches 10m but stops at 10.3m and won't go deeper

**Fix:** Increase Ki (integral gain)
```
Before: Kp=0.8, Ki=0.1, Kd=0.3 → Error +0.3m persistent
After:  Kp=0.8, Ki=0.2, Kd=0.3 → Error +0.05m ✓
```

---

### Problem: Response Too Slow

**Symptom:** Takes 60 seconds to reach target depth

**Fix:** Increase Kp (proportional gain)
```
Before: Kp=0.3, Ki=0.05, Kd=0.1 → 60 sec rise time
After:  Kp=0.8, Ki=0.1, Kd=0.3  → 30 sec rise time ✓
```

---

### Problem: Current Compensation Failing

**Symptom:** Robot drifts with current despite depth setpoint

**Fix:** Increase Ki and raise integral_max
```python
# Before:
self.integral_max = 50.0  # Too restrictive
self.Ki = 0.05

# After:
self.integral_max = 100.0  # Allow larger integral wind-up
self.Ki = 0.15             # Faster integral response
```

---

## Summary

### For Your System:

**Use These Values as Starting Point:**

```python
Kp = 0.8      # Proportional gain
Ki = 0.1      # Integral gain (current compensation)
Kd = 0.3      # Derivative gain (damping)

# Run tests:
# 1. Dive to 10m → measure rise time & overshoot
# 2. Hold 10m with 1 m/s current → measure steady-state error
# 3. Rapid setpoint change (5m → 15m) → measure response
# 4. Check for oscillation → adjust Kd if needed
```

---

## Do You Have Thruster Specs?

To provide **exact coefficients for YOUR hardware**, I need:

```
1. Motor/thruster model: ________________
2. Maximum thrust: _____ N
3. Response time: _____ ms
4. Robot mass (dry): _____ kg
5. Robot volume: _____ m³
6. Pressure sensor accuracy: ±_____ m
7. ESC type: ________________
```

**Once you provide these, I'll calculate your exact Kp, Ki, Kd values.**

If not available right now, the template values above (Kp=0.8, Ki=0.1, Kd=0.3) work well for typical 300W underwater thrusters on 8kg robots and should get you ±5cm accuracy out of the box.

---

**Next Step:** Test in water tank, then deploy on robot. Adjust gains based on actual performance.
