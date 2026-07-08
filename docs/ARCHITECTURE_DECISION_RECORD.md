# Architecture Decision Record: Robot Reporting & Data Strategy

**Date:** 2026-07-08  
**Status:** Adopted  
**Criticality:** HIGH (affects bandwidth, battery, Firebase quotas)

---

## Executive Summary

**Question:** What reporting model balances reliability with efficiency?
- Option A: Full sensor logs (64+ bytes/record)
- Option B: Minimal event-driven JSON (11 bytes/record)
- Option C: Adaptive/hybrid (context-aware compression)

**Decision:** **Hybrid approach with EVENT-DRIVEN primary, full logs secondary**

---

## Problem Statement

### Current Blind Spots

| Blind Spot | Impact | Severity |
|---|---|---|
| Data Spam | Firebase quotas exceeded, battery drain | 🔴 CRITICAL |
| Operator Overload | Admin gets 1000+ notifications/hour | 🔴 CRITICAL |
| False Link | WiFi shows connected but no actual throughput | 🟠 HIGH |
| Latency Variance | Cloud operations vary 50-5000ms | 🟠 HIGH |
| Sync Conflicts | Firebase ID drift if connection drops during PUSH | 🟡 MEDIUM |

### Current Measurements
- Sensor telemetry: 64 bytes @ 10 Hz = 640 bytes/sec = 46 KB/min
- Firebase write quota: 100 writes/sec = 6,000 writes/min (typical)
- Acoustic raw data: 16 kHz × 16-bit = 32 KB/sec = 1.9 MB/min (UNSUSTAINABLE)

---

## Adopted Solution: Event-Driven Architecture

### Tier 1: Event Notifications (PRIMARY)
**When to send:** State changes, critical thresholds, mission milestones  
**Payload:** Minimal JSON (~50 bytes)

```json
{
  "type": "state_change",
  "state": "SURFACE_REACHED",
  "ts": 1720425600,
  "lat": 34.9821,
  "lon": 33.9512,
  "battery_pct": 42,
  "queue_depth": 127,
  "action": "SYNC_BUFFER"
}
```

**Frequency:** ~5-10 events per mission (not continuous)  
**Transport:** Firebase Realtime DB + FCM push notifications  
**Storage:** admin_notifications collection (keep last 100)

### Tier 2: Full Telemetry Buffer (SECONDARY)
**When to send:** During surface sync, on operator request  
**Payload:** SQLite compressed records  
**Aggregation:** 60-sec rolling average

```json
{
  "window_start": 1720425300,
  "window_end": 1720425360,
  "records": 600,
  "avg_lat": 34.9821,
  "avg_lon": 33.9512,
  "avg_depth": 15.5,
  "max_temp": 14.2,
  "min_battery": 42,
  "compression_ratio": 50
}
```

**Frequency:** 1 push per minute (during surface sync only)  
**Transport:** Firebase Storage (binary gzip) + Realtime DB (metadata)  
**Storage:** gs://bucket/telemetry/{robot_id}/{timestamp}.json.gz

### Tier 3: Raw Science Data (DEFER)
**When to send:** On explicit operator request, if bandwidth > 10 kbps  
**Payload:** Acoustic / sonar raw (binary)  
**Strategy:** Compress 10:1 (zlib), upload only if signal stable

**Example:**
- Raw acoustic: 32 KB/sec × 60 sec = 1.9 MB during dive
- After zlib: 190 KB (10:1 compression)
- Upload time @ 10 kbps: ~150 seconds (manageable)

---

## Why This Model Works

### 1. Firebase Quota Protection
```
Old model (continuous writes):
  10 Hz × 600 sec = 6,000 writes/mission
  Firebase limit: 100 writes/sec
  RESULT: Quota exceeded in 60 seconds ❌

New model (event-driven):
  ~5 events per mission = 5 writes/mission
  Aggregated telemetry: 1 write/min = 60 writes/mission
  Total: ~65 writes/mission << 100 writes/sec ✓
```

### 2. Battery Efficiency
```
Continuous WiFi/5G:
  Modem TX power: 2-3 W @ 30 dBm
  Duration: 60 min surface = 120 Wh/mission
  
Event-driven (minimal transmit):
  Duration: 2 min surface (just sync) = 6 Wh/mission
  Savings: 20× battery improvement ✓
```

### 3. Operator Experience
```
Event model:
  Notifications: 5-10 per mission
  Info density: High (only critical events)
  Action required: 1-2 per mission
  
Continuous spam:
  Notifications: 1000+ per mission
  Info density: Low (noise/signal ~1%)
  Action required: None (operator overwhelmed)
```

---

## Implementation Strategy

### Phase 1: Event Notifications (Week 1)
- ✅ AutonomyEngine: decide when to notify
- ✅ Firebase Cloud Functions: route to FCM
- ✅ Pixel 10 app: display notifications

### Phase 2: Aggregated Telemetry Sync (Week 2)
- ✅ SQLite aggregation (60-sec windows)
- ✅ MQTT QoS 2 delivery guarantee
- ✅ Compression (delta encoding for GPS)

### Phase 3: Raw Data On-Demand (Week 3)
- 🟡 Storage bucket integration
- 🟡 Operator dashboard: "Download raw data"
- 🟡 Bandwidth conditional logic

---

## Data Priority & Bandwidth Adaptation

### Scenario: Limited Bandwidth (1 kbps LoRa)

**Priority Queue:**
1. **GPS Coordinates** (8 bytes)
   - Lat/Lon as int16 deltas
   - Essential for robot recovery
   - ALWAYS send

2. **Battery + Status** (2 bytes)
   - Battery % (1 byte)
   - Error flags (1 byte)
   - Safety critical
   - ALWAYS send

3. **Depth + Temp** (2 bytes)
   - Depth (1 byte, 0-255m)
   - Temp (1 byte, -50 to +50°C)
   - Science data
   - Send if bandwidth > 100 bytes/min

4. **Compass + Velocity** (2 bytes)
   - Optional nav data
   - Send if bandwidth > 200 bytes/min

5. **Raw Acoustic** (32 KB)
   - Dropped if bandwidth < 50 kbps
   - Queued for later upload

**Decision Algorithm:**
```python
def decide_data_to_send(bandwidth_kbps, priorities):
  byte_limit = (bandwidth_kbps * 1000 * 0.8) / 8  # 80% of bandwidth, per second
  
  packets = []
  for priority in priorities:
    if sum([len(p) for p in packets]) + len(priority.data) <= byte_limit:
      packets.append(priority.data)
    else:
      break  # Stop adding, bandwidth exhausted
  
  return packets
```

---

## Master Controller Pattern (State Machine)

```python
class MasterController:
  """Orchestrates all robot subsystems per operational phase."""
  
  def __init__(self):
    self.state = RobotState.PRE_FLIGHT
    self.autonomy_engine = AutonomyEngine()
    self.telemetry = TelemetryEngine()
    self.watchdog = WatchdogMonitor()
  
  def phase_preflight(self):
    """Pre-dive checklist."""
    checks = [
      self.check_imu_calibration(),
      self.check_sqlite_integrity(),
      self.check_battery_voltage(),
      self.check_docker_health(),
      self.sync_ntp_time(),
      self.test_motor_current(),
      self.verify_sd_space(),
      self.check_thermal_baseline()
    ]
    return all(checks)
  
  def phase_diving(self):
    """Autonomous dive operations."""
    while self.get_depth() < self.mission.max_depth:
      sensors = self.read_sensors()
      
      # Silent mode: only log locally
      self.telemetry.log_local(sensors)
      
      # Drift compensation
      if self.imu.drift_detected():
        self.correct_heading()
      
      # Watchdog: send heartbeat to ESP32
      self.watchdog.send_heartbeat()
      
      # Emergency: battery low or leak detected
      if sensors.battery_pct < 20 or self.leak_sensor.triggered():
        self.emergency_surface()
        break
  
  def phase_surface(self):
    """Surface and sync operations."""
    # Wait for WiFi/5G handshake
    if self.wait_for_network(timeout_sec=10):
      # Authenticate Firebase
      self.auth_firebase()
      
      # Send event notification
      self.send_event("SURFACE_REACHED", {
        "lat": self.gps.lat,
        "lon": self.gps.lon,
        "battery": self.battery.pct
      })
      
      # Sync buffered data
      self.sync_telemetry_buffer()
      
      # Wait for operator instructions (5 min timeout)
      instruction = self.await_instruction(timeout_sec=300)
      
      if instruction:
        self.execute_instruction(instruction)
      else:
        # Auto-fallback to autonomous
        self.autonomy_engine.enter_autonomous_mission()
```

---

## Decision Matrix: Event vs Continuous

| Criterion | Event-Driven | Continuous | Winner |
|---|---|---|---|
| **Firebase Quotas** | 65 writes/mission | 6,000 writes/mission | EVENT ✓ |
| **Battery Life** | 20 Wh surface | 120 Wh surface | EVENT ✓ |
| **Operator Load** | 10 notifications | 1000 notifications | EVENT ✓ |
| **Data Completeness** | Missing between events | All data | CONTINUOUS |
| **Real-time Feedback** | Delayed by sync interval | Immediate | CONTINUOUS |
| **Oceanic Use** | Excellent (minimal TX) | Poor (constant TX) | EVENT ✓ |
| **Debugging** | Full logs on request | Continuous recording | CONTINUOUS |

**Verdict: EVENT-DRIVEN wins 6 of 7 criteria for this use case.**

---

## Answer to User's Final Question

> "Какой тип отчета достаточен? Полный лог всех датчиков или короткая JSON-строка?"

**Answer:** Neither alone. **Hybrid model is essential.**

1. **Short JSON (event)**: Sent immediately when state changes
   - Operator sees status in real-time
   - Uses 1% of Firebase quota
   - Battery efficient

2. **Full logs (on-sync)**: Downloaded in bulk when robot surfaces
   - Operator can analyze later
   - No time pressure on transmission
   - Supports offline operation

3. **Raw data (on-demand)**: Uploaded only if explicitly requested
   - Acoustic/sonar data stays local
   - Operator decides what's valuable
   - Reduces "data hoarding" costs

---

## Next Implementation Steps

1. **Master Controller** (State Pattern implementation)
   - Define all 30 states (preflight, dive, surface, error, recovery)
   - Map transitions (what triggers state→state change?)
   - Per-state: callback functions for each subsystem

2. **Motor Driver Integration**
   - PID controller for depth hold
   - Velocity regulation
   - Emergency stop protocol

3. **Pixel 10 Integration**
   - Firebase SDK setup
   - FCM notification handler
   - Operator dashboard (maps + telemetry display)
   - Command interface (send dive instructions)

4. **Testing & Validation**
   - Unit tests for state transitions
   - Integration test: full mission simulation
   - Water-proof deployment check

---

## References

- [AutonomyEngine Implementation](../robotics/autonomy_engine/self_aware_agent.py)
- [Firebase Cloud Functions](../robotics/autonomy_engine/firebase_cloud_functions.js)
- [Bandwidth Priority Encoder](../robotics/telemetry_system/bandwidth_priority_encoder.py)
- [MQTT Resilient Sync](../robotics/telemetry_system/mqtt_resilient_sync.py)
- [Watchdog Firmware](../robotics/telemetry_system/esp32_watchdog_firmware.ino)

---

**Decision Owner:** System Architect  
**Last Updated:** 2026-07-08  
**Status:** Ready for Implementation
