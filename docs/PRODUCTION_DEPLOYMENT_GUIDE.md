# VKTEST Production Deployment Guide: AUV Autonomous Intelligence System

**Version:** 1.0  
**Last Updated:** 2026-07-29  
**Target Platform:** Raspberry Pi 3B+ with Docker  
**Deployment Environment:** Coastal waters (0-50m depth, 5-15°C)  
**Project Stage:** Phase 5 (Field Trial) → Phase 11 (Staged Rollout)

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Hardware Verification](#hardware-verification)
3. [Docker Build & Deployment](#docker-build--deployment)
4. [Network Configuration](#network-configuration)
5. [Monitoring & Observability](#monitoring--observability)
6. [Failure Modes & Recovery](#failure-modes--recovery)
7. [Blind Spot Mitigations](#blind-spot-mitigations)
8. [Emergency Procedures](#emergency-procedures)
9. [Post-Deployment Verification](#post-deployment-verification)

---

## Pre-Deployment Checklist

### ✅ Software Prerequisites

- [ ] Docker & docker-compose installed (v20.10+)
- [ ] Python 3.11+ with pip
- [ ] Git (for version control)
- [ ] SSH access to Raspberry Pi (via local network)
- [ ] All dependencies in `requirements.txt` installed

**Verify installation:**

```bash
docker --version           # Docker 20.10.17 or later
python3 --version          # Python 3.11.0 or later
docker-compose --version   # Docker Compose 1.29.2 or later
```

### ✅ Configuration Files

**Required before deployment:**

```bash
# Copy environment template to actual config
cp .env.template .env

# Edit with deployment-specific values
nano .env
```

**Critical .env variables:**

```bash
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-api-key
MQTT_BROKER_URL=mqtt://broker.local:1883
ROBOT_ID=rov-001
LOG_LEVEL=INFO              # Set to DEBUG only if debugging
DOCKER_MEMORY_LIMIT=768MB   # Raspberry Pi 3 has 1GB total
```

### ✅ SSL/TLS Certificates

For secure MQTT (QoS 2 over TLS):

```bash
mkdir -p certs/
# Copy certificates to certs/
ls -la certs/
# Should contain: ca.crt, client.crt, client.key
```

**Certificate verification:**

```bash
openssl verify -CAfile certs/ca.crt certs/client.crt
# Should print "OK"
```

### ✅ Database Initialization

SQLite offline buffer requires initial schema:

```bash
# Container initialization script will auto-create tables
# Verify post-deployment with:
docker-compose exec rov_agent sqlite3 /app/data/telemetry.db ".tables"
# Should show: telemetry_aggregate, telemetry_queue
```

---

## Hardware Verification

### Pre-Deployment Testing

**On Raspberry Pi 3:**

```bash
# 1. Verify RPi specs
cat /proc/cpuinfo | grep -E "processor|model name"
# Should show: Broadcom BCM2835 ARM processor

# 2. Check available memory
free -h
# Should show: ~900 MB available (1GB total - OS)

# 3. Verify storage
df -h /
# Should have >2 GB free for Docker images

# 4. Test network connectivity
ping 8.8.8.8 -c 1
# Should respond

# 5. Test SSH access from deployment machine
ssh pi@<rpi-ip>
# Should connect without password (key-based auth)
```

### GPIO Pin Verification (Watchdog ESP32 Integration)

**For watchdog power management:**

```bash
# Verify GPIO4 is available (watchdog EN pin)
gpio readall | grep "GPIO 4"
# Should show: GPIO 4 (BCM4) in INPUT/OUTPUT mode

# Test GPIO toggle
echo 4 > /sys/class/gpio/export
echo out > /sys/class/gpio/gpio4/direction
echo 1 > /sys/class/gpio/gpio4/value    # Set HIGH
echo 0 > /sys/class/gpio/gpio4/value    # Set LOW
```

### Sensor Connectivity Check

**Battery Manager (ADC):**

```bash
# Verify I2C connection to ADS1115 ADC (voltage measurement)
i2cdetect -y 1 | grep "48"
# Should show device at address 0x48
```

**Temperature Sensor (Thermistor/DS18B20):**

```bash
# If using DS18B20 (1-wire)
ls -la /sys/bus/w1/devices/ | grep "28-"
# Should list temperature sensor device
```

**Depth Sensor (BMP390):**

```bash
# Verify I2C connection to barometric sensor
i2cdetect -y 1 | grep "77"
# Should show device at address 0x77
```

---

## Docker Build & Deployment

### Build Docker Image

**On deployment machine (or RPi if sufficient disk space):**

```bash
# Build multi-stage image (optimized for arm32v7)
docker build -t rov-agent:latest -f Dockerfile .

# Tag for registry (if using Docker Hub or private registry)
docker tag rov-agent:latest docker.io/myuser/rov-agent:latest

# Push to registry (optional, for CI/CD)
docker push docker.io/myuser/rov-agent:latest
```

**Build verification:**

```bash
# Inspect image
docker inspect rov-agent:latest | grep "Architecture"
# Should show: "arm" or "arm32"

# Check image size
docker images rov-agent:latest
# Should be <500 MB (arm32v7 multi-stage keeps it lean)
```

### Deploy with Docker Compose

**Start all services:**

```bash
docker-compose up -d
# Should start 5 services: rov_agent, mqtt_broker, firebase_emulator, prometheus, grafana
```

**Verify services running:**

```bash
docker-compose ps
# All services should show "Up" status

# Check individual service logs
docker-compose logs rov_agent -f          # Real-time logs
docker-compose logs mqtt_broker --tail=10 # Last 10 lines
```

**Health check:**

```bash
# Check main service health endpoint
curl http://localhost:8080/health

# Should return JSON: {"status": "healthy", "uptime_sec": 123.45}
```

---

## Network Configuration

### Firewall & Port Management

**Required open ports:**

| Port | Service | Protocol | Direction |
|------|---------|----------|-----------|
| 8080 | REST API (health, status) | TCP | Inbound |
| 5000 | Dashboard (Grafana) | TCP | Inbound |
| 1883 | MQTT Broker | TCP | Inbound (local network) |
| 8883 | MQTT Broker (TLS) | TCP | Inbound (remote) |
| 9090 | Prometheus metrics | TCP | Inbound (monitoring) |
| 9000 | WebRTC (sonar streaming) | UDP | Bidirectional |

**UFW firewall rules (if enabled):**

```bash
sudo ufw allow 8080/tcp      # REST API
sudo ufw allow 5000/tcp      # Grafana
sudo ufw allow 1883/tcp      # MQTT
sudo ufw allow 8883/tcp      # MQTT TLS
sudo ufw allow 9090/tcp      # Prometheus
sudo ufw allow 9000/udp      # WebRTC
```

### DNS & Hostname Resolution

**Configure local DNS (if satellite/mesh network):**

```bash
# Edit /etc/hosts for offline access
sudo nano /etc/hosts
# Add entries:
# 192.168.1.100  mqtt.local
# 192.168.1.101  firebase.local
```

**Test DNS resilience:**

```bash
# Simulate DNS failure and recovery
nslookup mqtt.local
ping mqtt.local

# System should buffer locally when DNS fails, recover when restored
```

---

## Monitoring & Observability

### Prometheus Metrics Scraping

**Access Prometheus dashboard:**

```
http://localhost:9090
```

**Key metrics to monitor:**

```promql
# CPU usage of rov_agent container
container_cpu_usage_seconds_total{name="rov_agent"}

# Memory usage
container_memory_usage_bytes{name="rov_agent"} / 1024 / 1024  # In MB

# Network errors (DNS, timeouts)
mqtt_connection_failures_total

# Battery status
battery_voltage_v, battery_soc_pct, battery_state

# Telemetry queue depth
telemetry_queue_depth

# Watchdog heartbeats
watchdog_heartbeat_count, watchdog_timeout_count
```

### Grafana Dashboards

**Access Grafana:**

```
http://localhost:3000
Username: admin
Password: admin
```

**Pre-built dashboards (should be imported):**

1. **System Health Dashboard**
   - CPU/memory usage, disk I/O
   - Network latency to MQTT broker
   - Uptime and restart count

2. **Telemetry Dashboard**
   - Sensor readings (depth, temp, battery)
   - Queue depth and aggregation rate
   - Firebase write quota usage

3. **Watchdog & Recovery Dashboard**
   - Heartbeat interval (target: 10 sec ± 1 sec)
   - Timeout count and recovery time
   - GPIO trigger history

### Logging Best Practices

**Log levels:**

```python
DEBUG    # Verbose (only when debugging specific issues)
INFO     # Normal operation, significant events
WARNING  # Recoverable errors, degraded operation
ERROR    # Unrecoverable errors, service impact
CRITICAL # System-level failures, emergency shutdown
```

**Configure log rotation:**

```bash
# Check docker log size limit
docker inspect rov_agent | grep -A 5 "LogConfig"

# Set max log size in docker-compose.yml
# logging:
#   driver: "json-file"
#   options:
#     max-size: "10m"
#     max-file: "3"
```

**View logs:**

```bash
# Real-time logs (follow mode)
docker-compose logs -f rov_agent

# Last N lines
docker-compose logs rov_agent --tail=100

# Filtered by log level
docker-compose logs rov_agent | grep "ERROR"
```

---

## Failure Modes & Recovery

### Battery-Related Failures

**Symptom:** Voltage drops below critical threshold (10.8V)

**Detection:**

```python
if battery_voltage < critical_voltage:
    # Triggered by BatteryManager state machine
    state = BatteryState.CRITICAL
    on_voltage_warning("critical", reading)
```

**Recovery:**

1. Mission enters EMERGENCY state
2. Thrusters reduced to 30% power (conserve energy)
3. All non-critical telemetry paused
4. Acoustic modem sends "EMERGENCY_SURFACE" to topside
5. AUV returns to surface at 0.2 m/s ascent

**Verification:**

```bash
# Monitor battery status
docker-compose exec rov_agent python3 -c "
from robotics.power.battery_manager import BatteryManager
bm = BatteryManager()
status = bm.get_status()
print(f'State: {status[\"state\"]}, Voltage: {status[\"voltage_v\"]}V')
"
```

### Network Failures (DNS/MQTT)

**Symptom:** Cannot resolve MQTT broker hostname, connection times out

**Detection:**

```python
# ResilienceMonitor catches socket.gaierror
except socket.gaierror:
    last_disconnect_reason = "DNS_FAILURE"
    connection_state = "OFFLINE"
```

**Recovery:**

1. Switch to SQLite offline buffer (automatic)
2. Data queued locally with 60-second aggregation
3. Every 5 seconds, attempt reconnection
4. On successful reconnection, flush buffer to MQTT

**Verification:**

```bash
# Simulate DNS failure
sudo iptables -A OUTPUT -d 8.8.8.8 -j DROP

# Monitor recovery
docker-compose logs rov_agent | grep -E "DNS|OFFLINE|recovered"

# Restore connectivity
sudo iptables -D OUTPUT -d 8.8.8.8 -j DROP
```

### Watchdog Timeout

**Symptom:** No heartbeat from Raspberry Pi for >30 seconds

**Detection:** ESP32-S3 watchdog triggers

**Recovery:**

1. ESP32 pulls GPIO EN pin LOW (cuts power to RPi)
2. Wait 3 seconds (power discharge)
3. Release GPIO EN pin (power restored)
4. RPi boots cleanly, systemd restarts services
5. ~30-45 second total recovery time

**Verification:**

```bash
# Monitor watchdog status
docker-compose exec rov_agent python3 -c "
from robotics.watchdog.esp32_watchdog import ESP32Watchdog
wd = ESP32Watchdog()
status = wd.get_status()
print(f'Heartbeats: {status[\"heartbeat_count\"]}, Timeouts: {status[\"timeout_count\"]}')
"
```

### Thermal Throttling

**Symptom:** CPU temperature >80°C, performance degraded

**Detection:**

```bash
vcgencmd measure_temp  # RPi3 native command
# Expected: temp=65.1'C (safe range: <75°C)
```

**Mitigation:**

1. Reduce sampling rate from 10 Hz → 5 Hz
2. Pause sonar streaming (if active)
3. Enable throttle notification to operator
4. If temp >85°C, abort mission (safety)

**Verification:**

```bash
# Monitor thermal status
watch -n 2 'vcgencmd measure_temp'

# If throttling detected
vcgencmd get_throttled
# Non-zero output indicates throttling event
```

---

## Blind Spot Mitigations

### 1. **Watchdog Recovery Failure**

**Blind Spot:** What if power-cycle recovery fails? (e.g., GPIO malfunction)

**Mitigation:**
- Implement secondary timeout: If RPi doesn't respond after 60 seconds (2× normal recovery time), operator receives critical alert
- Fallback: Manual power cycle via topside power relay
- Logging: All watchdog events logged to MQTT for post-mission analysis

**Test Procedure:**

```bash
# Simulate GPIO failure (block watchdog pin)
echo 4 > /sys/class/gpio/export
echo in > /sys/class/gpio/gpio4/direction  # Lock as input (prevents writes)
# Now watchdog cannot pull pin LOW

# Verify system handles gracefully:
# - Watchdog timeout should not crash RPi
# - Operator receives fallback alert
# - Manual recovery instructions sent
```

### 2. **Firebase Quota Exhaustion**

**Blind Spot:** Event-driven telemetry may still exceed quota under heavy activity

**Mitigation:**
- Tier-based bucketing: Only CRITICAL events write to Firebase (emergency, dock lock, mission complete)
- SAFETY/SCIENCE events → MQTT + local buffer
- Daily quota monitor: If 80% consumed, reduce sampling rate automatically
- Buffer flush only during SURFACE_IDLE phase (controlled batch)

**Monitoring:**

```bash
# Check Firebase quota usage
curl -X GET "https://firebaserestapi.googleapis.com/v1beta1/projects/PROJECT_ID/usage" \
  -H "Authorization: Bearer $TOKEN"

# Alert if >80% consumed
if usage_percent > 80:
    log.warning("Firebase quota 80% exhausted, reducing telemetry rate")
```

### 3. **UWB Lock-On Failure at Dock**

**Blind Spot:** Signal fading may prevent dock alignment (±10 cm requirement)

**Mitigation:**
- Dual-receiver MRC combining (3 dB gain, 5-10% success improvement)
- Fallback sequence:
  1. UWB lock attempt (10 seconds timeout)
  2. If fails: Switch to acoustic positioning (±1m)
  3. Visual alignment via topside camera (if available)
  4. Manual dock via RC control
- Timeout: If lock not achieved in 60 seconds, mission aborts to safe zone

**Testing:**

```bash
# Verify lock-on success rate in tank
# Expected: >95% @ 3m with dual diversity receiver
# Measured: Loop 100 lock attempts, measure success %
success_rate = (successful_locks / 100) * 100
assert success_rate > 95, f"Lock-on success {success_rate}% < 95% target"
```

### 4. **Acoustic Multipath Interference**

**Blind Spot:** Thermocline reflections create 500 ns delay spread, causes intersymbol interference

**Mitigation:**
- Equalization: Adaptive RAKE receiver (DW1000 built-in CIR capture)
- Frequency agility: If multipath detected (CIR spread >400 ns), switch to 2.4 GHz fallback
- Preamble correlation: Use redundant spreading code (12 symbols) for robust timing sync

**Detection:**

```bash
# Capture channel impulse response (CIR) and analyze
cir = dwm1000.get_cir()
delay_spread = compute_rms_delay_spread(cir)

if delay_spread > 400e-9:  # 400 ns threshold
    log.warning(f"High multipath detected (spread {delay_spread*1e9:.0f} ns)")
    # Trigger equalization or frequency switch
```

### 5. **Brownout During High-Thruster Draw**

**Blind Spot:** 5V rail sag under simultaneous 2A draw (full thruster + sensors)

**Mitigation:**
- Pre-dive voltage test: Require V > 12V before DIVING state (ensure margin)
- Current limiting: Soft-start thrusters (ramp over 100 ms, not instant)
- Power sequencing: Sensors powered BEFORE thrusters
- Reserve capacity: Maintain 10% battery for emergency

**Verification:**

```bash
# Test brownout scenario (simulate high draw)
# Expected: Voltage sag <1V (e.g., 12V → 11V), recovers within 500 ms

# Measure actual sag in controlled environment
initial_voltage = measure_voltage()
apply_high_current_load(2.0)  # 2A draw
sleep(0.1)
sag_voltage = measure_voltage()
sag_depth_v = initial_voltage - sag_voltage

assert sag_depth_v < 1.0, f"Sag too deep: {sag_depth_v}V"
```

### 6. **Data Corruption in Serial/Network**

**Blind Spot:** Electromagnetic interference or bit flips in UWB/UART may corrupt packets

**Mitigation:**
- CRC32 integrity checking: Every packet includes 32-bit CRC
- Sequence ID tracking: Detect out-of-order or duplicate packets
- Automatic retry: MQTT QoS 2 (exactly-once delivery)
- Protocol version field: Enables future protocol changes without breaking old firmware

**Verification:**

```bash
# Test packet integrity
from robotics.protocol.protobuf_serializer import ProtobufSerializer

serializer = ProtobufSerializer()
msg = create_test_message()
packed = serializer.pack(msg)

# Simulate corruption (flip one bit)
corrupted = bytearray(packed)
corrupted[10] ^= 0x01  # Flip bit in middle

# Should detect corruption
try:
    unpacked = serializer.unpack(corrupted)
    assert False, "Should have detected CRC failure"
except ValueError as e:
    assert "CRC" in str(e)  # CRC check failed as expected
```

---

## Emergency Procedures

### 🔴 Loss of Communication (>5 minutes no contact)

**Operator Actions:**

1. Attempt to establish topside-to-AUV acoustic link
2. If unsuccessful, activate emergency beacon (pinger)
3. Check Raspberry Pi power/connectivity via WiFi
4. If still no response after 10 minutes, declare AUV lost

**AUV Autonomous Actions:**

```python
# After 5 minutes no Firebase command
if time.time() - last_command_time > 300:
    log.critical("No command from operator for 5 min, entering autonomous return")
    mission_state = OperationalPhase.SURFACE_IDLE
    heading = compute_home_vector()  # Return to launch point
    ascent_rate = 0.2  # m/s safe ascent
```

### 🔴 Pressure Sensor Failure (cannot measure depth)

**Detection:**

```python
# Pressure reading stuck or nonsensical
if pressure_reading == prev_pressure_reading:
    sensor_failure_count += 1
    if sensor_failure_count > 10:
        log.critical("Pressure sensor failure detected")
```

**Recovery:**

1. Switch to altitude-based depth estimation (sonar + inertial)
2. Reduce maximum depth to 10m (conservative safety limit)
3. Increase ascent monitoring frequency (5 Hz)
4. Log sensor failure for post-mission analysis

### 🔴 Battery Critical (V < 10.8V)

**Immediate Actions:**

1. Reduce thruster power to 20%
2. Pause all non-critical telemetry
3. Send "BATTERY_CRITICAL" alert via acoustic modem
4. Ascend at 0.1 m/s (energy-efficient rate)
5. Shutdown ETA calculation, navigate to surface only

**Recovery Procedure:**

1. Surface and allow 30-minute charge (if solar panel available)
2. Verify voltage recovery to >11.5V before re-dive
3. Reduce planned mission depth/duration by 20%

### 🔴 Motor/Thruster Failure

**Detection:**

```python
# Thruster response lag >500 ms or no response
if thruster_response_time > 500e-3 or not thruster_responding:
    failed_thruster_id = identify_failed_thruster()
    log.critical(f"Thruster {failed_thruster_id} failure")
```

**Recovery:**

1. Compensate with remaining thrusters (asymmetric power distribution)
2. Reduce speed by 50%
3. Disable maneuvers (pitch/roll) that require failed thruster
4. Maintain heading using remaining motors
5. Return to surface under differential thrust

**Verification:**

```bash
# Test thruster failure scenario
for thruster_id in [1, 2, 3, 4, 5, 6]:
    disable_thruster(thruster_id)
    
    # Verify AUV still controllable
    result = execute_turn_test(target_heading=90)
    assert result.success, f"Cannot turn without thruster {thruster_id}"
    
    enable_thruster(thruster_id)
```

---

## Post-Deployment Verification

### First-Run Checklist

After starting docker-compose:

- [ ] **Services healthy:** All 5 containers show "Up" status
- [ ] **Logs clean:** No ERROR/CRITICAL messages in first 30 seconds
- [ ] **REST API responsive:** `curl http://localhost:8080/health` returns 200
- [ ] **Sensors online:** All 6 sensors report readings (depth, temp, battery, etc.)
- [ ] **Watchdog connected:** ESP32 confirms heartbeat (check logs)
- [ ] **MQTT broker active:** Can publish test message to /test topic
- [ ] **Prometheus scraping:** Metrics visible in http://localhost:9090
- [ ] **Preflight checks pass:** System validates all 33 preflight conditions

### Performance Baseline (Establish Metrics)

```bash
# Measure baseline resource usage (idle)
# CPU: should be <15%
# Memory: should be <150 MB
# Network: should be <100 Kbps

# Measure baseline during active mission (10 Hz control loop)
# CPU: should be <40%
# Memory: should be <300 MB
# Network: should be <1 Mbps

# Log these baselines for comparison
echo "Baseline CPU: $(top -bn1 | grep 'rov_agent' | awk '{print $3}')%"
echo "Baseline Memory: $(docker stats rov_agent --no-stream --format '{{.MemUsage}}' | cut -d' ' -f1)"
```

### Sensor Calibration Verification

**Depth sensor (BMP390):**

```bash
# Measure on surface (should be ~1 atm = 0m depth)
docker-compose exec rov_agent python3 -c "
from robotics.motor_control.pid_depth_controller import DepthSensorCalibration
cal = DepthSensorCalibration()
reading = cal.pressure_to_depth_m(101325)  # Sea-level pressure
assert abs(reading) < 1, f'Depth offset > 1m: {reading}m'
"
```

**Temperature sensor:**

```bash
# Compare thermistor reading with reference thermometer
actual_temp = measure_with_reference_thermometer()
reported_temp = get_system_temperature()
assert abs(actual_temp - reported_temp) < 2, f'Temp error: {abs(actual_temp - reported_temp)}°C'
```

**Battery voltage:**

```bash
# Measure actual battery voltage with multimeter
# Compare to system reading
actual_voltage = measure_with_multimeter()
reported_voltage = get_battery_voltage()
assert abs(actual_voltage - reported_voltage) < 0.2, f'Voltage error: {abs(actual_voltage - reported_voltage)}V'
```

### Dock Alignment Dry-Run

**Before ocean deployment, test dock alignment in pool:**

1. Place dock at known distance (3m) from AUV
2. Run dock alignment sequence (UWB lock-on)
3. Measure final position error (should be <±10 cm)
4. Repeat 20 times, calculate success rate (target: >95%)
5. Log all position estimates for accuracy analysis

```bash
# Test dock alignment success rate
success_count = 0
for attempt in range(20):
    result = test_dock_alignment()
    if result.position_error < 0.1:  # ±10 cm
        success_count += 1

success_rate = (success_count / 20) * 100
print(f"Dock alignment success: {success_rate}%")
assert success_rate >= 95, f"Success rate {success_rate}% below 95% target"
```

---

## Deployment Troubleshooting

### Issue: Container keeps restarting

**Check logs:**

```bash
docker-compose logs rov_agent --tail=50
# Look for pattern in error messages
```

**Common causes:**
- Missing environment variables → Fix: Update .env
- Sensor not responding → Fix: Verify I2C/serial connections
- Watchdog timeout → Fix: Check CPU usage, reduce sampling rate

### Issue: MQTT connection fails

**Diagnosis:**

```bash
# Verify broker is running
docker-compose logs mqtt_broker

# Test connectivity
docker-compose exec rov_agent nc -zv mqtt 1883
# Should print: Connection to mqtt 1883 port [tcp/mqtt] succeeded!
```

### Issue: Low memory (container OOMKilled)

**Increase memory limit in docker-compose.yml:**

```yaml
services:
  rov_agent:
    mem_limit: 1gb  # Increase from 768mb
```

**Or reduce memory usage:**
- Decrease history buffer size (default: 1000 readings)
- Disable detailed logging (set to WARNING level)
- Reduce sensor sampling rate (10 Hz → 5 Hz)

### Issue: Network latency high (>500 ms)

**Diagnose network quality:**

```bash
docker-compose exec rov_agent python3 -c "
import socket, time
start = time.time()
socket.gethostbyname('mqtt')
latency = (time.time() - start) * 1000
print(f'DNS latency: {latency:.1f} ms')
"
```

**Mitigation:**
- Use local IP instead of hostname (e.g., 192.168.1.100)
- Reduce MQTT QoS from 2 (exactly-once) to 1 (at-least-once)
- Enable local buffer aggregation (60 sec → 30 sec windows)

---

## Rollback Procedures

If deployed version has critical issues:

```bash
# Stop current version
docker-compose down

# Revert to previous Docker image
docker tag rov-agent:latest rov-agent:broken
docker tag rov-agent:v0.9.2 rov-agent:latest

# Restart with previous version
docker-compose up -d

# Verify health
curl http://localhost:8080/health
```

---

## Success Criteria (Go/No-Go Decision)

**Before ocean deployment, ALL of these must pass:**

✅ **Functional:**
- All 33 preflight checks pass
- Dock alignment success rate ≥95% (20-trial pool test)
- Mission control from operator interface functional
- Emergency surface procedure tested and verified

✅ **Reliability:**
- Watchdog timeout/recovery < 60 seconds (measured 5×)
- Battery cold-start detection functioning
- MQTT offline buffering verified (data recovery on reconnection)
- No memory leaks (monitor for 1 hour continuous operation)

✅ **Safety:**
- Thermal throttling detection active and responsive
- All 6 thrusters respond correctly
- Sensor failure handling tested (pressure/temp/battery)
- Emergency procedures documented and crew trained

✅ **Performance:**
- CPU usage <40% during active mission
- Memory stable (no unbounded growth)
- Network latency <100 ms to MQTT broker
- Telemetry queue never exceeds 1000 messages

---

## Contact & Support

**For deployment issues:**
- GitHub Issues: https://github.com/leonidy431/VKTEST/issues
- Internal Slack: #vktest-deployment

**Key contacts:**
- Project Lead: [name]
- Hardware Integration: [name]
- Network/Ops: [name]

**Documentation links:**
- [CLAUDE.md](../CLAUDE.md) - Project overview & standards
- [ADVANCED_ARCHITECTURE_SYNTHESIS.md](./ADVANCED_ARCHITECTURE_SYNTHESIS.md) - System design
- [OPERATIONAL_STANDARDS_99.md](./OPERATIONAL_STANDARDS_99.md) - 99 procedures

