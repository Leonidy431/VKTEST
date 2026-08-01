# VKTEST: Autonomous Underwater Reconnaissance Complex

**Status:** Architecture Design Complete, Ready for Field Testing  
**Last Updated:** 2026-07-08  

## Overview

VKTEST is an autonomous underwater vehicle (AUV) control system for deep-sea reconnaissance with:

- **Autonomous Navigation:** FSM-driven edge intelligence (48 parameters)
- **Depth Stabilization:** PID controller (±5 cm accuracy)
- **Real-time Visualization:** PointPillars 3D neural network on Pixel 10
- **Dual-Stack Connectivity:** Firebase (control) + WebRTC (data plane)
- **Offline Resilience:** SQLite buffer + MQTT fallback + autonomous homing
- **Hardware Safety:** ESP32 watchdog + thermal throttling + battery monitoring

## Architecture

```
Pixel 10 Pro XL (Operator)
   │
   ├─ Firebase Control Plane (Events, Commands)
   │
   └─ WebRTC Data Plane (Sonar Streaming, 1+ Gbps mmWave)
   
Raspberry Pi 3 (Robot)
   ├─ AutonomousAgent FSM (48-parameter SystemState)
   ├─ PID Depth Controller (±5 cm)
   ├─ SQLite Buffer (offline persistence)
   ├─ Sensor Integration (BMP390, MPU6050, sonar)
   ├─ Motor Control (vertical + horizontal thrusters)
   └─ ESP32 Watchdog (heartbeat monitor)

MQTT Broker (Fallback)
   └─ Resilient QoS 2 delivery
```

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- 512 MB free disk space

### Local Testing
```bash
pip install -r requirements.txt
python robotics/autonomous_agent_main.py --use-mock-hardware
```

### Docker Deployment
```bash
docker build -t rov-agent:latest .
docker-compose up -d
curl http://localhost:8080/health
```

## Mission Phases

### Phase 1: Preflight (30 min)
Execute 33-item checklist: battery, sensors, thrusters, thermal

### Phase 2: Diving (variable)
Silent mode: SQLite buffering + local FSM (no Firebase TX)
PID maintains depth, sonar buffers locally, autonomous decisions

### Phase 3: Surface Sync (10 min)
Upload buffered telemetry, receive commands, charge battery

## Documentation

| Document | Purpose |
|---|---|
| `docs/ARCHITECTURE_DECISION_RECORD.md` | Event-driven model rationale |
| `docs/ADVANCED_ARCHITECTURE_SYNTHESIS.md` | Dual-stack channel, FSM, blind spot solutions |
| `docs/OPERATIONAL_STANDARDS_99.md` | 99 operational instructions + PID tuning |
| `docs/MMWAVE_RESEARCH_3D_SCANNING.md` | Hardware analysis (Pixel 10, TI IWR6843) |

## Configuration

Create `.env`:
```bash
FIREBASE_PROJECT_ID=your-project
MQTT_BROKER_URL=mqtt://localhost:1883
ROBOT_ID=rov-001
LOG_LEVEL=DEBUG
```

## Development

```bash
pytest robotics/tests/ -v          # Run tests
black robotics/                    # Format code
pylint robotics/                   # Lint
mypy robotics/                     # Type check
```

## Troubleshooting

**Robot not responding:**
```bash
mosquitto_sub -h localhost -t "robot/heartbeat"  # Check MQTT
echo -n "S" > /dev/ttyUSB0                        # Check watchdog
```

**Depth oscillation:**
Reduce Kp (proportional gain), increase Kd (derivative)

**Battery drain:**
Disable WebRTC during dive, reduce sonar FPS, check motor current

## Support

Generate diagnostic bundle:
```bash
docker exec rov_agent python robotics/diagnostics.py --bundle
```

Post-mission analysis:
```bash
python robotics/scripts/plot_mission.py /tmp/rov_buffer_rov-001.db
```

## References

- Protocol Buffers: `robotics/protocol/robot_data.proto`
- Motor Control: `robotics/motor_control/pid_depth_controller.py`
- Autonomy Engine: `robotics/autonomy_engine/self_aware_agent.py`
- Docker: `docker-compose.yml` + `Dockerfile`

## Version History

| Version | Date | Status |
|---|---|---|
| 1.0 | 2026-07-08 | Architecture Design Complete |
| 0.9 | 2026-07-01 | Advanced Synthesis |
| 0.8 | 2026-06-25 | Protocol Buffers |
| 0.7 | 2026-06-20 | Autonomy Engine |
| 0.6 | 2026-06-15 | Architecture Decision |

**Next Milestone:** Field deployment (Phase 3: WebRTC streaming)

