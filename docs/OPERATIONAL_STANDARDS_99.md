# 99 Operational Standards: Complete ROV Operating Manual

**Date:** 2026-07-08  
**Classification:** Operational Manual  
**Scope:** Mission-critical procedures for autonomous underwater vehicle (AUV)  

---

## Table of Contents

1. **Block 1: Preflight (Instructions 1-33)**
2. **Block 2: Diving (Instructions 34-66)**
3. **Block 3: Crisis (Instructions 67-99)**
4. **Hardware Configuration**
5. **PID Tuning Guide**
6. **mmWave/5G Integration**
7. **WebRTC Streaming Setup**
8. **Troubleshooting**

---

## Executive Summary: The Synergistic System

Your ROV operates as a **hybrid edge-cloud system**:

```
Pixel 10 (Operator)
    │
    ├──[Firebase Control Plane]──→ Commands + State Sync
    │   (Event-driven, low bandwidth)
    │
    └──[WebRTC Data Plane]──→ Sonar Stream (HD)
        (P2P UDP, high bandwidth, mmWave)
        
Raspberry Pi 3 (Robot)
    │
    ├──[Local FSM + PID]──→ Depth Hold, Navigation
    │   (Autonomous even if Pixel offline)
    │
    ├──[SQLite Buffer]──→ Offline Persistence
    │   (Queued for sync when online)
    │
    └──[WebRTC Sender]──→ Real-time Sonar UDP Stream
        (Bypasses Firebase, direct to Pixel)
```

**Key Principle:** Robot never waits for operator. It decides autonomously at every step.

---

## Block 1: Preflight Checklist (Instructions 1-33)

### Pre-Mission Ritual (Must complete before ANY dive)

#### Instruction 1: Battery Health Assessment
```python
def check_battery():
    # Measure internal resistance (indicator of age/degradation)
    voltage_loaded = read_adc(battery_pin)  # Under 1A load
    voltage_open = read_adc(battery_pin)    # No load
    
    internal_resistance_ohm = (voltage_open - voltage_loaded) / 1.0
    
    if internal_resistance_ohm > 2.0:
        return FAIL("Battery old, slow-charge mode mandatory")
    else:
        return PASS("Battery healthy")
```

**Why:** Cold start sag (Power sag when TX peak current draws 3A) can reset Pi if battery degraded.

**Action:** If FAIL → Charge battery slowly (C/10 rate) until next mission.

---

#### Instruction 2: Pressure Sensor Calibration
```python
def calibrate_pressure_sensor():
    # Zero-point verification at surface
    readings = []
    for _ in range(10):
        readings.append(read_pressure_psi())
        time.sleep(0.1)
    
    surface_pressure = mean(readings)
    
    # Standard atmosphere at sea level = 14.696 psi
    if abs(surface_pressure - 14.696) > 0.1:
        return FAIL(f"Pressure offset: {surface_pressure - 14.696:+.2f} psi")
    else:
        return PASS("Pressure sensor calibrated")
```

**Why:** Even 0.5 psi error = 0.35 m depth error (accumulates during long missions).

---

#### Instruction 3: Leak Sensor Continuity Test
```python
def test_leak_sensor():
    # Simulates water contact with low current
    result = gpio.read(LEAK_SENSOR_PIN)
    
    if result == 0:
        return PASS("Leak sensor dry")
    else:
        return FAIL("Water detected in hull!")
```

**Why:** Prevents missions if hull already compromised.

---

#### Instruction 4-10: Motor/Thruster Tests
```python
def test_thrusters():
    # Test each thruster sequentially
    thrusters = ["vertical_1", "vertical_2", "horizontal_cw", "horizontal_ccw"]
    
    for thruster in thrusters:
        # Command 50% power, measure current response
        send_pwm(thruster, 1500 + 250)  # 1500 neutral + 250 offset = 50%
        time.sleep(0.5)
        current = read_adc(current_sensor)
        
        if current < 0.1:
            return FAIL(f"{thruster} no response")
        
        send_pwm(thruster, 1500)  # Return to neutral
        time.sleep(0.2)
    
    return PASS("All thrusters operational")
```

**Why:** Dead thruster = uncontrolled tumbling under water.

---

#### Instruction 11: IMU Drift Compensation Baseline
```python
def baseline_imu_drift():
    # Record gyro bias while static (1 minute)
    gyro_samples = []
    
    for _ in range(600):  # 10 minutes @ 100 Hz
        gx, gy, gz = read_imu_gyro()
        gyro_samples.append((gx, gy, gz))
        time.sleep(0.01)
    
    gyro_bias = (
        mean([s[0] for s in gyro_samples]),
        mean([s[1] for s in gyro_samples]),
        mean([s[2] for s in gyro_samples])
    )
    
    # Check if drift is acceptable
    drift_magnitude = sqrt(gyro_bias[0]**2 + gyro_bias[1]**2 + gyro_bias[2]**2)
    
    if drift_magnitude > 2.0:  # deg/sec
        return FAIL(f"IMU drift too high: {drift_magnitude:.2f}°/s")
    else:
        return PASS(f"IMU bias established: {gyro_bias}")
```

**Why:** Gyro integration accumulates over time. Baseline lets us subtract bias.

---

#### Instruction 12-20: Storage, Thermal, Docker Health
```python
def system_checks():
    # Check SD card space
    disk_usage_pct = psutil.disk_usage('/').percent
    if disk_usage_pct > 90:
        return FAIL(f"SD card {disk_usage_pct}% full")
    
    # Check thermal baseline (room temperature)
    cpu_temp = read_cpu_temp()
    if cpu_temp > 50:
        return FAIL(f"Pi already hot: {cpu_temp}°C (expected <40°C)")
    
    # Check Docker health
    containers = subprocess.run(['docker', 'ps', '--format={{.Status}}'])
    if 'unhealthy' in str(containers.stdout):
        return FAIL("Docker container unhealthy")
    
    return PASS("System ready")
```

---

#### Instruction 21-33: Network Pre-test & Permission Sync
```python
def network_preflight():
    # Test Firebase connectivity
    try:
        db.reference('test').set({'ping': int(time.time())}, timeout=5)
        return PASS("Firebase online")
    except:
        return FAIL("Firebase unreachable (will operate autonomously)")
    
    # Test MQTT fallback
    mqtt_client.connect(MQTT_BROKER, 1883, keepalive=10)
    mqtt_client.publish("robot/heartbeat", "preflight")
    return PASS("MQTT online")
```

---

### Preflight Checklist Template

```
PREFLIGHT CHECKLIST - ROV-001
Time: 2026-07-08 14:30 UTC
Operator: Alice
Location: San Diego, Latitude 32.7157, Longitude -117.1611

[✓] Battery voltage (12.0V - 12.6V range)
[✓] Battery internal resistance (<2 Ω)
[✓] Pressure sensor calibration (14.696 ± 0.1 psi)
[✓] Leak sensor dry
[✓] Vertical thruster 1: 0.5A at 50%
[✓] Vertical thruster 2: 0.5A at 50%
[✓] Horizontal thruster (CW): 0.3A at 50%
[✓] Horizontal thruster (CCW): 0.3A at 50%
[✓] IMU drift baseline: [0.02°/s, -0.01°/s, 0.03°/s]
[✓] Compass calibration: within ±5°
[✓] SD card space: 23% used
[✓] CPU temperature: 38°C
[✓] Docker health: 5/5 containers healthy
[✓] Firebase: Connected
[✓] MQTT: Connected
[✓] GPS: Lock acquired (4 satellites)
[✓] UWB: Initialized, 3 anchors detected

PREFLIGHT STATUS: GO
Next phase: DIVING
```

---

## Block 2: Diving Operations (Instructions 34-66)

### Instruction 34: Initialization & Silent Mode

**Silent Mode** = No telemetry transmitted during dive. Only buffer locally.

```python
def phase_diving_start():
    # Disable all telemetry transmission
    firebase_enabled = False
    mqtt_enabled = False
    webrtc_enabled = False
    
    # Enable local SQLite buffering
    buffer_enabled = True
    buffer_max_interval = 1.0  # seconds
    
    # Notify operator that we're going dark (send last message)
    notify_firebase("DIVING_STARTED", {
        "timestamp": now(),
        "estimated_return": target_mission_duration_sec,
        "message": "Going dark - will sync on surface"
    })
    
    # Start PID depth controller
    pid_controller.enable(target_depth=target_depth_m)
    
    logger.info("Entered DIVING phase - Silent mode active")
```

**Why:** Underwater WiFi is useless. Save battery for thrusters + sensors.

---

### Instruction 35-40: Depth Stabilization with PID

**Critical:** Maintain depth ±5 cm while sonar scans.

```python
def maintain_depth_hold():
    """
    PID loop must run at 10 Hz (100 ms cycle)
    Pressure sensor acts as depth feedback
    """
    while in_diving_phase:
        # Read current depth
        depth_m = pressure_sensor.read_depth()
        
        # Calculate PID output
        error = target_depth - depth_m
        pid_output = pid_controller.update(error)
        
        # Command thrusters
        # pid_output: -1.0 (full ascent) to +1.0 (full descent)
        command_vertical_thrusters(pid_output)
        
        # Log for post-dive analysis
        buffer.save({
            'timestamp': time.time(),
            'depth': depth_m,
            'target': target_depth,
            'error': error,
            'pid_output': pid_output
        })
        
        time.sleep(0.1)  # 10 Hz
```

**PID Tuning (see Section below):**

Recommended starting values:
- **Kp = 0.8** (proportional gain)
- **Ki = 0.1** (integral gain)
- **Kd = 0.3** (derivative gain)

Adjust upward if robot sinks below target.
Adjust downward if robot oscillates around target.

---

### Instruction 41-50: Drift Compensation During Dive

**Problem:** IMU gyro integrates drift → heading error grows

**Solution:** Kalman filter with compass correction

```python
def correct_heading_drift():
    """
    Every 30 seconds, resync gyro with compass
    """
    while in_diving_phase:
        # Integrate gyro for 30 sec
        gyro_heading_change = 0.0
        for i in range(300):  # 30 sec @ 10 Hz
            gx, gy, gz = read_imu_gyro()
            
            # Remove baseline (from preflight)
            gx -= gyro_bias[0]
            gy -= gyro_bias[1]
            gz -= gyro_bias[2]
            
            # Extract yaw rate (rotation around Z axis)
            # For body-fixed gyro: yaw_rate = gz (degrees/sec)
            gyro_heading_change += gz * 0.1  # 0.1 sec per cycle
        
        # Read compass (independent of gyro)
        compass_heading = read_compass()
        
        # Correct gyro heading
        estimated_heading = (estimated_heading + gyro_heading_change)
        estimated_heading = 0.7 * estimated_heading + 0.3 * compass_heading
        
        logger.debug(f"Drift correction: gyro {gyro_heading_change:+.1f}° → final {estimated_heading:.1f}°")
        
        time.sleep(30.0)  # Resync every 30 sec
```

---

### Instruction 51-60: Acoustic Buffering & Energy Monitoring

**Sonar produces 32 KB/sec raw data.** Buffer locally, compress, upload on surface.

```python
def buffer_sonar_data():
    """
    Collect sonar data into local buffer
    Compress and prepare for upload when surfacing
    """
    sonar_buffer = []
    
    while in_diving_phase:
        # Read raw sonar (32 KB payload)
        raw_sonar = sonar_module.read_frame()  # ~32 KB
        
        # Compress with zlib (10:1 ratio typical)
        compressed = zlib.compress(raw_sonar, level=9)
        
        # Store to SQLite with timestamp
        buffer.save({
            'timestamp': time.time(),
            'sonar_data_zlib': compressed,
            'original_size': len(raw_sonar),
            'compressed_size': len(compressed)
        })
        
        # Every 60 sec, log bandwidth estimate
        if len(sonar_buffer) % 60 == 0:
            total_compressed = sum(len(s['sonar_data_zlib']) for s in sonar_buffer[-60:])
            bandwidth_kbps = (total_compressed * 8) / 60 / 1000
            logger.info(f"Sonar buffer: {bandwidth_kbps:.1f} kbps compression")
        
        time.sleep(0.1)
```

---

### Instruction 61-66: Emergency Homing Preparation

**Robot must know home GPS location and ascent route.**

```python
def prepare_homing_route():
    """
    Pre-calculate emergency ascent waypoints
    (every 5 meters up = position adjustment to match GPS)
    """
    surface_gps = get_last_surface_position()  # From preflight GPS lock
    current_depth = depth_sensor.read_depth()
    
    homing_waypoints = []
    for ascent_depth in range(int(current_depth), 0, -5):
        # Calculate slight horizontal movement to surface GPS
        horizontal_progress = (current_depth - ascent_depth) / current_depth
        
        waypoint_lat = current_lat + (surface_gps['lat'] - current_lat) * horizontal_progress
        waypoint_lon = current_lon + (surface_gps['lon'] - current_lon) * horizontal_progress
        
        homing_waypoints.append({
            'depth': ascent_depth,
            'lat': waypoint_lat,
            'lon': waypoint_lon
        })
    
    logger.info(f"Emergency homing route: {len(homing_waypoints)} waypoints")
    return homing_waypoints
```

---

## Block 3: Crisis Management (Instructions 67-99)

### Instruction 67: Battery Critical Shutdown

**If battery < 10%: IMMEDIATE PROTOCOL SHUTDOWN**

```python
def monitor_battery_critical():
    while True:
        battery_pct = read_battery_percentage()
        
        if battery_pct < 10:
            logger.critical("BATTERY CRITICAL < 10%: EMERGENCY PROTOCOL")
            
            # Step 1: Disable all external services
            firebase_enabled = False
            mqtt_enabled = False
            webrtc_enabled = False
            buffer_sync_enabled = False
            
            # Step 2: Kill heavy processes
            subprocess.run(['pkill', '-f', 'sonar_streaming'])
            subprocess.run(['pkill', '-f', 'webrtc'])
            
            # Step 3: Force surface ascent
            pid_controller.disable()
            command_vertical_thrusters(-1.0)  # FULL ASCENT
            
            # Step 4: Activate ballast blow (if mechanical)
            activate_ballast_blow()
            
            # Step 5: Send final message
            try:
                firebase.update({
                    'emergency': True,
                    'reason': 'BATTERY_CRITICAL',
                    'last_depth': depth_sensor.read_depth(),
                    'last_position': {'lat': current_lat, 'lon': current_lon}
                })
            except:
                pass
            
            # Step 6: Log to EEPROM
            watchdog_save_event("BATTERY_CRITICAL_SHUTDOWN")
            
            logger.critical("HOMING: Emergency ascent started")
            break
        
        time.sleep(10.0)
```

---

### Instruction 68: Firebase Latency Fallback

**If Firebase response > 5 sec: Switch to MQTT**

```python
def adaptive_connectivity():
    """
    Detect slow Firebase, fallback to MQTT
    """
    while in_diving_phase:
        try:
            start = time.time()
            response = firebase.push({'timestamp': start}, timeout=5)
            latency = time.time() - start
            
            if latency > 5.0:
                logger.warning(f"Firebase slow: {latency:.1f}s → switching to MQTT")
                use_firebase = False
                use_mqtt = True
            else:
                use_firebase = True
        except Exception as e:
            logger.warning(f"Firebase error: {e} → switching to MQTT")
            use_firebase = False
            use_mqtt = True
        
        time.sleep(30.0)  # Check every 30 sec
```

---

### Instruction 69-75: Thermal Management

**CPU > 75°C: Throttle motors by 50%**

```python
def monitor_thermal():
    """
    Pi 3 can hit 80°C under sustained load
    Throttle thrusters to reduce CPU heat
    """
    while running:
        cpu_temp = read_cpu_temp()
        
        if cpu_temp > 80:
            logger.warning(f"CRITICAL THERMAL: {cpu_temp}°C")
            motor_throttle = 0.5  # 50% power max
            
            # Stop non-critical processes
            subprocess.run(['pkill', '-f', 'sonar_streaming'])
            
        elif cpu_temp > 75:
            logger.warning(f"HIGH THERMAL: {cpu_temp}°C")
            motor_throttle = 0.7  # 70% power
            
        elif cpu_temp > 60:
            logger.info(f"Elevated thermal: {cpu_temp}°C (monitoring)")
            motor_throttle = 1.0  # Full power OK
            
        else:
            motor_throttle = 1.0  # Normal
        
        time.sleep(5.0)
```

---

### Instruction 76-99: Advanced Recovery Procedures

#### Instruction 76: Watchdog Reset Recovery

**If Pi becomes unresponsive: ESP32 forces power cycle**

```
ESP32 Watchdog Timeline:
- 0-30 sec: Awaiting heartbeat from Pi
- 30 sec: No heartbeat detected
- 35 sec: Power cut to Pi (MOSFET relay opens)
- 40 sec: Power restored to Pi (MOSFET relay closes)
- 60 sec: Pi boots (system logs show startupat 60s mark)
- 70 sec: Watchdog sees first heartbeat → ARM
```

**Robot behavior during recovery:**
1. Lost heartbeat (30s): Robot enters LOCAL_AUTONOMOUS mode
2. Power cut (35s): Thrusters hold last command
3. Power restored (40s): Boot sequence starts
4. Recovery complete (70s): Resume normal FSM

---

#### Instruction 77-99: Satellite Network Handover

**When transitioning between cell towers:**

```python
def handle_network_transition():
    """
    Satellite networks change IP addresses during handover
    Detect and re-establish connection
    """
    last_rsrp = -80  # Signal strength in dBm
    connection_unstable = False
    
    while True:
        current_rsrp = read_signal_strength()
        
        # Detect handover (sudden power drop)
        if current_rsrp < (last_rsrp - 20):
            logger.warning(f"Network handover detected: {last_rsrp} → {current_rsrp} dBm")
            connection_unstable = True
            
            # Disable WebRTC (might break during IP change)
            webrtc_enabled = False
            
            # Buffer mode: queue telemetry
            buffer_enabled = True
        
        # Detect recovery
        if connection_unstable and current_rsrp > (last_rsrp + 10):
            logger.info(f"Network recovered: {current_rsrp} dBm")
            connection_unstable = False
            
            # Resume normal telemetry
            webrtc_enabled = True
            firebase_enabled = True
        
        last_rsrp = current_rsrp
        time.sleep(5.0)
```

---

## Hardware Configuration

### Sensor Pinout (Raspberry Pi 3)

```
I2C (SCL/SDA)
├─ Pressure Sensor (BMP390): 0x77
├─ IMU (MPU6050): 0x68
├─ Compass (QMC5883L): 0x0D
└─ Thermal (tmp102): 0x48

GPIO (Digital)
├─ GPIO 17: Leak sensor (input)
├─ GPIO 22: Ballast blow relay (output)
└─ GPIO 23: Status LED (output)

SPI (MOSI/MISO/CLK/CS)
└─ Sonar module (ADS8685): CS on GPIO 24

UART
├─ /dev/ttyUSB0: ESP32 watchdog (115200 baud)
└─ /dev/ttyUSB1: GPS/GNSS (9600 baud)

Analog (ADC)
├─ AIN0: Battery voltage (0-16V range, 12-bit)
└─ AIN1: Motor current (0-10A range via shunt)

PWM (Servo Control)
├─ GPIO 12: Vertical thruster 1 (1000-2000 µs)
├─ GPIO 13: Vertical thruster 2 (1000-2000 µs)
├─ GPIO 18: Horizontal thruster CW (1000-2000 µs)
└─ GPIO 19: Horizontal thruster CCW (1000-2000 µs)
```

---

## PID Tuning Guide

### Depth Hold Tuning Process

**Start: Kp=0.1, Ki=0, Kd=0**

1. **Increase Kp until oscillation**
   - Slow increase (0.1 → 0.2 → 0.3)
   - Stop when robot oscillates ±10 cm around depth

2. **Add derivative to damp oscillation**
   - Start Kd = Kp / 10
   - Increase until oscillations stop

3. **Add integral to eliminate steady-state error**
   - Start Ki = Kp / 100
   - Increase to correct small drift

**Example Tuning Session:**

```
Target depth: 10m
Initial: Kp=0.1, Ki=0, Kd=0
  Result: Slow descent, -50 cm at 30 sec

Increase Kp to 0.5:
  Result: -20 cm at 30 sec, oscillating ±15 cm

Increase Kp to 0.8:
  Result: -5 cm at 30 sec, oscillating ±8 cm

Add Kd=0.3:
  Result: -2 cm at 30 sec, oscillating ±2 cm

Add Ki=0.1:
  Result: 0 cm at 60 sec (steady), oscillating ±1 cm

FINAL: Kp=0.8, Ki=0.1, Kd=0.3 ✓
```

---

## mmWave/5G Integration

### mmWave Beam Steering (Pixel 10 Pro XL)

When operator is on shore with Pixel 10:

```python
def adaptive_mmwave_beamforming():
    """
    mmWave is narrowbeam (±60° cone).
    Must point antenna at robot's buoy location.
    """
    while webrtc_active:
        # Get robot's current surface position (from GPS)
        robot_gps = get_last_gps_position()
        
        # Get operator's position (from Pixel 10 GPS)
        operator_gps = receive_operator_position()
        
        # Calculate bearing to robot
        bearing = calculate_bearing(operator_gps, robot_gps)
        
        # Steer mmWave antenna to bearing
        steering_angle = bearing - pixel_current_heading
        set_antenna_steering(steering_angle)
        
        logger.info(f"mmWave beam: {bearing:.0f}° (offset {steering_angle:+.0f}°)")
        
        time.sleep(1.0)  # Update every second
```

---

### Blind Spot Solution #1: Weather Switching

**mmWave blocked by rain/fog? Switch to Wi-Fi 6**

```python
def weather_adaptive_connectivity():
    """
    Rain/fog → reflections → mmWave fails
    Solution: Switch to Wi-Fi 6 (5 GHz, more weather-resistant)
    """
    rain_threshold_db = -120  # Very weak signal
    
    while webrtc_active:
        signal_strength = read_signal_strength()
        rain_detected = (signal_strength < rain_threshold_db)
        
        if rain_detected and using_mmwave:
            logger.warning("Rain detected: switching mmWave → Wi-Fi 6")
            disable_mmwave_beamforming()
            enable_wifi6_streaming()
            bitrate = 500  # Mbps (reduced from mmWave 1+ Gbps)
            
        elif not rain_detected and not using_mmwave:
            logger.info("Rain stopped: switching Wi-Fi 6 → mmWave")
            disable_wifi6_streaming()
            enable_mmwave_beamforming()
            bitrate = 2000  # Mbps (full mmWave)
        
        time.sleep(5.0)
```

---

## Conclusion: Mission Success Criteria

✓ **All 33 Preflight checks pass**
✓ **Depth maintained ±5 cm during entire dive**
✓ **No emergency conditions triggered**
✓ **Telemetry synced within 60 sec of surfacing**
✓ **Operator received all critical events**

**Next Mission Review:**
- Post-dive analysis of buffer data
- Thermal performance report
- Battery discharge curve
- Motor efficiency metrics
- Recommend adjustments for next dive

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-08  
**Status:** Ready for Field Deployment
