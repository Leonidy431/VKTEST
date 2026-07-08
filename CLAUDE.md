# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Summary

**VKTEST** is an autonomous underwater vehicle (AUV) reconnaissance system combining event-driven telemetry, edge intelligence FSM, PID depth stabilization, and dual-stack connectivity (Firebase control plane + WebRTC data plane). Target hardware: Raspberry Pi 3 edge compute with Pixel 10 Pro XL operator interface.

**Branch for development:** `claude/phased-array-robotics-nhh6i2`

---

## Quick Commands

### Setup
```bash
pip install -r requirements.txt
python robotics/autonomous_agent_main.py --use-mock-hardware
```

### Testing
```bash
pytest tests/ -v                          # All tests
pytest tests/test_pid_controller.py -v    # Single test file
pytest -k "test_depth_hold" -v            # Filter by test name
```

### Linting & Formatting
```bash
black robotics/                           # Format code (PEP8)
pylint robotics/                          # Lint with warnings
mypy robotics/                            # Type checking
```

### Docker
```bash
docker build -t rov-agent:latest .
docker-compose up -d
docker-compose logs -f rov_agent
curl http://localhost:8080/health
```

### Git Workflow
```bash
git fetch origin claude/phased-array-robotics-nhh6i2
git checkout claude/phased-array-robotics-nhh6i2
# Make changes...
git add robotics/ docs/
git commit -m "Describe change"
git push -u origin claude/phased-array-robotics-nhh6i2
```

---

## Architecture Overview

### 4-Layer System Design

```
Layer 4: Pixel 10 Pro XL (Operator Interface)
         PointPillars 3D neural network | FCM notifications | Dashboard UI
         
Layer 3: Firebase (Control Plane) + WebRTC (Data Plane)
         Events, commands, ACKs     | Sonar streaming (1+ Gbps mmWave)
         
Layer 2: Raspberry Pi 3 Docker Container (Edge Intelligence)
         AutonomousAgent FSM | PID Depth Controller | Telemetry Engine
         
Layer 1: Hardware (Sensors, Thrusters, Watchdog)
         BMP390 (depth) | MPU6050 (IMU) | ESP32-S3 (watchdog) | T200 motors
```

### Dual-Stack Channel Strategy

- **Control Plane (Firebase):** Low-bandwidth command/ACK/event signaling (~65 writes/mission, 50 bytes each)
- **Data Plane (WebRTC/UDP):** High-bandwidth sonar/sensor telemetry (1+ Gbps adaptive)
- **Fallback (MQTT QoS 2):** Exactly-once delivery when Firebase latency >5 sec
- **Local Buffer (SQLite):** Offline persistence during silent dive mode

### FSM: OperationalPhase States

```
PREFLIGHT (33 checks) → DIVING (silent mode, local FSM) 
  ↓                        ↓
  EMERGENCY ←─ BATTERY <10% / LEAK DETECTED
  ↓
  SURFACE_IDLE (sync + recharge) ← DIVING (Battery <20%)
```

### SystemState: 48-Parameter Decision Model

| Group | Count | Parameters |
|-------|-------|-----------|
| Navigation | 6 | pitch, roll, yaw, depth, heading, velocity |
| Safety | 6 | battery_pct, leak_detected, temperature_c, pressure_psi, motor_current_a, error_flags |
| Mission | 6 | target_depth, mission_type, waypoint_index, gps_lat, gps_lon, time_remaining_sec |
| Communication | 6 | connection_quality, signal_strength_dbm, firebase_online, mqtt_online, webrtc_active, last_contact_sec |
| Sensor Data | 12 | temperature_water, salinity_ppt, acoustic_energy, sonar_distance, battery_voltage, imu_drift_deg, compass_error_deg, queue_depth, buffer_usage_pct, cpu_usage_pct, memory_usage_pct, thermal_status |
| Autonomy | 6 | autonomy_mode, estimated_return_time_sec, homing_active, emergency_state, watchdog_count, last_action |

---

## Module Map

### Core Orchestration
- **`robotics/autonomous_agent_main.py`** (450 lines)
  - Entry point for Docker container
  - Runs 10 Hz main control loop in separate thread
  - Integrates all subsystems: sensors, FSM, PID, telemetry, Firebase, watchdog
  - Exports `AutonomousAgent` class with `start()`, `stop()`, `get_status()` methods

### Motor Control
- **`robotics/motor_control/pid_depth_controller.py`** (443 lines)
  - `PIDDepthController` class: proportional-integral-derivative control
  - Anti-windup protection, derivative filtering (alpha=0.7), slew rate limiting
  - `DepthSensorCalibration`: pressure→depth conversion (saltwater 1025 kg/m³)
  - Mock classes for testing without hardware
  - **Key tuning:** Ziegler-Nichols method; defaults: Kp=0.8, Ki=0.1, Kd=0.3

### Telemetry & Communication
- **`robotics/telemetry_system/telemetry_robot.py`**
  - `TelemetryEngine` class: aggregates sensor readings
  
- **`robotics/telemetry_system/mqtt_resilient_sync.py`** (700+ lines)
  - `MQTTResiliencyManager`: QoS 2 fallback when Firebase offline
  - `ResilienceMonitor`: exponential backoff on DNS failures (socket.gaierror)
  - `SQLiteOfflineBuffer`: 60-sec rolling average aggregation
  
- **`robotics/telemetry_system/bandwidth_priority_encoder.py`** (600+ lines)
  - `DataPriority` enum: CRITICAL, SAFETY, SCIENCE, TELEMETRY, DEBUG
  - `BandwidthPriorityQueue`: adaptive dropping under congestion
  - `BandwidthAdaptiveEncoder`: congestion detection

### Autonomy Engine
- **`robotics/autonomy_engine/self_aware_agent.py`** (400+ lines)
  - `RobotState` enum: 7 states (DIVING_AUTONOMOUS, DIVING_CONNECTED, SURFACING, etc.)
  - `ActionType` enum: decision actions (SEND_STATUS_REPORT, EXECUTE_OPERATOR_CMD, etc.)
  - `ChannelQuality` dataclass: signal/latency/packet-loss scoring
  - `AutonomyEngine` base class with `evaluate_decision()` FSM logic
  - `FirebaseAutonomyEngine`: production Firebase integration

### Protocol & Serialization
- **`robotics/protocol/robot_data.proto`** (168 lines)
  - Protobuf message schema: TelemetryMessage, CommandMessage, CommandAck, EventNotification, RobotMessage
  - Includes: sequence_id (out-of-order detection), timestamp_unix_ms, crc32 (corruption detection)
  
- **`robotics/protocol/protobuf_serializer.py`** (422 lines)
  - `ProtobufSerializer` class: pack/unpack binary protocol
  - CRC32 integrity checking
  - Sequence ID wraparound handling (32-bit)
  - Firebase hex encoding for safe JSON transport

### Infrastructure
- **`Dockerfile`** (102 lines)
  - Multi-stage arm32v7 build (builder → runtime)
  - Non-root user 'rover'
  - Health check via Python script
  - Entrypoint: `autonomous_agent_main.py`

- **`docker-compose.yml`** (199 lines)
  - 5 services: rov_agent, mqtt_broker, firebase_emulator, prometheus, grafana
  - rov_agent: privileged, host network, /dev/shm 512MB, mem_limit 768MB
  - Port mappings: 9000 UDP (WebRTC), 8080 TCP (REST API), 5000 TCP (Dashboard)

---

## Documentation Structure

| Document | Focus | When to Read |
|----------|-------|--------------|
| `docs/ARCHITECTURE_DECISION_RECORD.md` | Event-driven model, Firebase quota reduction (6000→65 writes/mission), Tier 1/2/3 data strategy | Understanding why we chose event-driven over full logging |
| `docs/ADVANCED_ARCHITECTURE_SYNTHESIS.md` | Dual-stack channels, Layer 1-4 system design, 99 operational procedures, 3 blind spot solutions | Grasping entire end-to-end architecture |
| `docs/OPERATIONAL_STANDARDS_99.md` | Block 1 (33 preflight checks), Block 2 (33 diving ops), Block 3 (33 crisis procedures), PID tuning guide, hardware pinout | Implementing preflight/diving/crisis logic or tuning motors |
| `docs/THRUSTER_SPECIFICATION_TEMPLATE.md` | Motor specs, static thrust testing, PID coefficient calculation (Ziegler-Nichols worked example with T500) | Characterizing new thrusters or validating PID gains |
| `docs/HARDWARE_PLATFORM_SELECTION.md` | BlueROV2 vs Chinese ROV comparison, proprietary lockdown risks, Guru assembly strategy (BlueROV2 Heavy + Jetson Orin), cost breakdown | Platform evaluation or justifying hardware choices |
| `docs/ARCHITECTURE_CLOSURE.md` | Status summary, strengths/weaknesses, 8-week timeline, immediate action items, FAQ | Current project status and next steps |
| `docs/MMWAVE_RESEARCH_3D_SCANNING.md` | Pixel 10 mmWave capabilities, Qualcomm TEE restrictions, TI IWR6843 alternative | Understanding 3D perception options |

---

## Key Architectural Decisions

### 1. Event-Driven Telemetry (Not Full Logging)
- **Why:** Firebase quota exhaustion (free tier: 100 writes/sec = 6,000 writes/10 min mission exceeds limits)
- **Solution:** ~65 writes/mission via event model (5-10 critical events + 1 write/min rolling average)
- **Blind Spot Addressed:** "Data Spam" and operator overload
- **Trade-off:** Can't replay every sensor reading; instead capture only state transitions

### 2. Dual-Stack Channels (Firebase Control + WebRTC Data)
- **Why:** Firebase write quota insufficient for high-bandwidth sonar streaming
- **Solution:** Split: Firebase for control (low-latency events), WebRTC/UDP for data (1+ Gbps)
- **Fallback:** MQTT QoS 2 when Firebase latency >5 sec
- **Blind Spot Addressed:** "Network bottleneck" and latency variance

### 3. SQLite Local Buffering + Silent Mode
- **Why:** Battery drain during dive (WiFi radio active = 500 mW drain)
- **Solution:** Disable Firebase TX during dive; buffer to SQLite; sync on surface
- **Benefit:** 20× battery improvement (120 Wh → 6 Wh for typical mission)
- **Blind Spot Addressed:** "Power sag during operations"

### 4. Protocol Buffers (Binary) Instead of JSON
- **Why:** 80% traffic reduction (JSON 100 bytes → Protobuf 20 bytes per telemetry)
- **Solution:** `robot_data.proto` schema with CRC32 integrity + sequence ID tracking
- **Blind Spot Addressed:** "Protocol corruption" and out-of-order packet detection

### 5. ESP32-S3 Watchdog (30-sec Heartbeat Timeout)
- **Why:** Raspberry Pi can hang/thermal-throttle; need external recovery mechanism
- **Solution:** ESP32-S3 listens for 'H' heartbeat every 10 sec; force power cycle if no signal for 30 sec
- **Blind Spot Addressed:** "Watchdog recovery" in crisis scenarios

### 6. 5-Minute Operator Timeout (Autonomous Fallback)
- **Why:** Operator may lose connectivity or ignore robot; robot should not wait indefinitely
- **Solution:** FSM autonomously returns home or continues mission if no Firebase command for 5 min
- **Blind Spot Addressed:** "Administrative bottleneck" (operator as single point of failure)

### 7. Firebase Cloud Functions (Rule Engine)
- 5 main triggers: AdminNotification, RobotStateChange, CommandReceived, OperatorTimeoutCheck, SyncComplete
- Auto-sync on SURFACE_IDLE, daily log export, FCM notifications to operator

---

## Development Guidelines

### Code Style
- **PEP8:** All Python code formatted with Black
- **Type Hints:** Use type annotations throughout
- **Docstrings:** One-liner for non-obvious WHY (not WHAT); reserved for architectural rationale
- **No Comments:** Variable names + docstrings are sufficient; don't duplicate code logic in comments

### Testing Strategy
- Unit tests in `tests/` directory (one file per module)
- Mock hardware classes (`MockDepthSensor`, `MockThrusterDriver`) for offline testing
- Test preflight checks, FSM state transitions, PID stability
- Run `pytest tests/ -v` before each commit

### Branching & Commits
- Develop on `claude/phased-array-robotics-nhh6i2`
- Commit message format: "Concise present-tense summary of change"
- Push with `-u` flag: `git push -u origin claude/phased-array-robotics-nhh6i2`
- Create PR as draft after pushing (auto-checks CI)

### Configuration
- `.env` file required:
  ```bash
  FIREBASE_PROJECT_ID=your-project
  FIREBASE_API_KEY=your-key
  MQTT_BROKER_URL=mqtt://localhost:1883
  ROBOT_ID=rov-001
  LOG_LEVEL=DEBUG
  ```

### Documentation in Code
- **All conversations and design decisions documented in PEP8 format**
- Architectural changes → update `docs/ADVANCED_ARCHITECTURE_SYNTHESIS.md`
- Operational procedures → update `docs/OPERATIONAL_STANDARDS_99.md`
- Motor tuning changes → update `docs/THRUSTER_SPECIFICATION_TEMPLATE.md`
- Platform decisions → update `docs/HARDWARE_PLATFORM_SELECTION.md`

---

## Common Workflows

### Add a New Sensor
1. Create sensor class in `robotics/motor_control/` or `robotics/telemetry_system/`
2. Add mock class for testing (inherit from abstract base)
3. Integrate into `_initialize_components()` in `AutonomousAgent`
4. Update `SystemState` dataclass with new fields
5. Add read logic to `_read_sensors()`
6. Write unit tests in `tests/test_<sensor>.py`

### Debug Depth Oscillation
1. Check PID gains in `pid_depth_controller.py` (defaults: Kp=0.8, Ki=0.1, Kd=0.3)
2. Reduce Kp proportionally to overshoot amount
3. Increase Kd to damp derivative
4. Run step-response test in `tests/test_pid_controller.py`
5. See `docs/THRUSTER_SPECIFICATION_TEMPLATE.md` for Ziegler-Nichols tuning

### Run Pre-Flight Checklist
1. Execute `python robotics/autonomous_agent_main.py --use-mock-hardware`
2. Verify all 33 checks pass in `_run_preflight_checks()`
3. Check battery >11V, leak sensor normal, thermal <50°C
4. Verify SQLite buffer initialized at `/tmp/rov_buffer_rov-001.db`

### Deploy to Raspberry Pi 3
1. Build Docker image: `docker build -t rov-agent:latest .`
2. Run docker-compose: `docker-compose up -d`
3. Check health: `curl http://localhost:8080/health`
4. Monitor logs: `docker-compose logs -f rov_agent`
5. Access Grafana dashboard: `http://localhost:3000` (password: admin)

---

## Blind Spots & Mitigations

| Blind Spot | Cause | Mitigation | Related Doc |
|-----------|-------|-----------|-------------|
| Data Spam | Firebase quota exhaustion | Event-driven model (65 writes/mission) | ARCHITECTURE_DECISION_RECORD.md |
| Operator Bottleneck | Admin unavailable | 5-min autonomous fallback + homing | AUTONOMY_GUIDE.md (implicit) |
| Network Latency | Firebase variable responsiveness | MQTT QoS 2 fallback (>5 sec threshold) | ARCHITECTURE_DECISION_RECORD.md |
| Power Sag | WiFi radio drain during dive | Silent mode + SQLite buffer + surface sync | OPERATIONAL_STANDARDS_99.md |
| Watchdog Failure | Pi unresponsiveness | ESP32-S3 30-sec heartbeat + force power cycle | OPERATIONAL_STANDARDS_99.md |
| Protocol Corruption | Binary data transmission | Sequence ID + CRC32 integrity checking | robot_data.proto, protobuf_serializer.py |
| Out-of-Order Packets | WebRTC/UDP unreliability | Sequence gap detection in ProtobufDeserializer | ProtobufDeserializer.kt |
| Cold Start | Battery voltage sag at startup | Pre-dive voltage check (>11V threshold) | OPERATIONAL_STANDARDS_99.md |

---

## Performance & Sizing

- **Control Loop Frequency:** 10 Hz (100 ms cycle time)
- **Watchdog Heartbeat:** 10 sec interval (30 sec timeout)
- **Firebase Write Reduction:** 99% (6,000 → 65 writes/mission)
- **Battery Efficiency:** 20× improvement via silent mode (6 Wh vs 120 Wh)
- **Telemetry Protocol:** 80% size reduction (JSON → Protobuf)
- **Depth Accuracy:** ±5 cm (PID tuned via Ziegler-Nichols)
- **Docker Memory:** 768 MB cap (Pi 3 has 1 GB total)
- **Sonar Streaming:** 1+ Gbps mmWave over WebRTC/UDP

---

## Reference

- **Main Entry Point:** `robotics/autonomous_agent_main.py`
- **Test Suite:** `tests/test_*.py`
- **Protocol Definition:** `robotics/protocol/robot_data.proto`
- **Configuration:** `.env` (create from template)
- **Docker Setup:** `Dockerfile` + `docker-compose.yml`
- **Architecture Docs:** `docs/ADVANCED_ARCHITECTURE_SYNTHESIS.md` (start here)

