---
name: vktest-autonomy-patterns
description: VKTEST-specific patterns for autonomous underwater vehicle development. Use when implementing FSM logic, PID tuning, telemetry buffering, or sensor integration to avoid architectural regressions.
license: MIT
---

# VKTEST Autonomy Patterns

Patterns and anti-patterns specific to the VKTEST autonomous underwater vehicle system.

**Scope:** Applies to core subsystems (AutonomousAgent, PIDDepthController, TelemetryEngine, AutonomyEngine, ProtobufSerializer).

---

## Pattern 1: FSM State Transitions

**Do:**
- Verify transition guards (battery level, leak detection, timeout) before state change
- Log state transitions with reason (why we moved from DIVING to SURFACING)
- Test each transition path in `tests/test_state_machine.py`
- Keep transition logic in `_evaluate_fsm()` only

**Don't:**
- Embed transition logic inside action execution
- Add intermediate states without architectural review (currently: 5 states are sufficient)
- Silent state changes (always log the reason)
- Trigger side effects during state transition (do that in `_execute_action()`)

**Anti-pattern:** Adding new state RETURNING_HOME without updating FSM tests, MQTT fallback logic, and watchdog heartbeat handling.

---

## Pattern 2: PID Depth Stabilization

**Do:**
- Use default gains (Kp=0.8, Ki=0.1, Kd=0.3) as starting point
- Apply Ziegler-Nichols tuning for new thruster models (see `docs/THRUSTER_SPECIFICATION_TEMPLATE.md`)
- Test with `tests/test_pid_controller.py` (step response, steady-state error, overshoot)
- Monitor integral windup (anti-windup limit = 0.5)

**Don't:**
- Add adaptive tuning without test suite for corner cases (cold water, 0°C salinity change)
- Modify slew rate limiting (currently 5 m/s) without understanding thruster ESC limits
- Remove derivative low-pass filtering (alpha=0.7 prevents oscillation)

**Anti-pattern:** "Let's auto-tune based on first 10 measurements" without understanding that PID is sensitive to temperature and buoyancy drift.

---

## Pattern 3: Telemetry Buffering & Sync

**Do:**
- Buffer to SQLite during silent mode (no Firebase TX during dive)
- Use 60-sec rolling average for telemetry rollup (1 write/min to Firebase)
- Verify sequence IDs and CRC32 checksums in `protobuf_serializer.py`
- Fall back to MQTT QoS 2 when Firebase latency >5 sec

**Don't:**
- Send raw sensor data every 100ms (quota exhaustion: 6,000 writes/mission)
- Mix multiple data priorities in single query (split by DataPriority enum)
- Skip sequence ID validation (enables detection of out-of-order packets)
- Assume Firebase is always online (local fallback + watchdog required)

**Anti-pattern:** "I'll sync all buffered data when connection returns" without handling duplicate ACKs or partial sync state.

---

## Pattern 4: Sensor Integration

**Do:**
- Create mock class for testing (`MockDepthSensor`, `MockThrusterDriver`)
- Add new field to `SystemState` dataclass
- Read sensor in `_read_sensors()` at 10 Hz rate
- Update documentation in `docs/OPERATIONAL_STANDARDS_99.md`

**Don't:**
- Add sensor without unit test (`tests/test_<sensor>.py`)
- Block main loop on sensor failure (wrap in try/except, log error, continue)
- Assume sensor value is calibrated (check `DepthSensorCalibration` for offset/scale)
- Store unbounded raw values (apply low-pass filtering or bounds check)

**Anti-pattern:** Adding a thermal sensor that sometimes returns -999°C and crashing the FSM because no bounds checking exists.

---

## Pattern 5: Watchdog Heartbeat

**Do:**
- Send 'H' heartbeat every 10 sec over UART to ESP32-S3
- Log heartbeat count in `SystemState.watchdog_count`
- Verify 30-sec timeout logic in hardware (ESP32 resets Pi on silence)
- Test watchdog recovery flow manually on hardware

**Don't:**
- Change heartbeat interval without consulting hardware team (ESP32 firmware is hardcoded)
- Assume UART is open (check `self.watchdog_serial_port` is not None)
- Block main loop waiting for watchdog ACK (send async, continue loop)

**Anti-pattern:** Watchdog timing skew causing false positives during high CPU load (happens at 80%+ CPU usage due to GIL).

---

## Pattern 6: Firebase vs MQTT Decision

**Use Firebase when:**
- Low-latency operator commands needed (<1 sec)
- State sync required (robot online/offline status)
- Operator actively monitoring (not silent dive phase)

**Use MQTT QoS 2 when:**
- Firebase latency >5 sec (measured via ping gateway)
- Executing pre-loaded mission (operator offline)
- Battery low (<20%) and need power saving

**Don't mix blindly:**
- Query Firebase AND MQTT for same data (causes deduplication nightmare)
- Assume Firebase writes are atomic (use command IDs and ACK protocol)

**Anti-pattern:** "Sync everything to both Firebase and MQTT" = doubled traffic, no actual reliability gain.

---

## Pattern 7: Protocol Robustness

**Do:**
- Use Protobuf for binary serialization (80% size reduction vs JSON)
- Include CRC32 checksum in every message (detects corruption)
- Track sequence IDs (detects duplicate/out-of-order packets)
- Test serialization round-trip in `tests/test_protocol.py`

**Don't:**
- Assume WebRTC/UDP delivers all packets in order (it doesn't)
- Send bare JSON without length prefix (message framing ambiguous)
- Ignore CRC failures (they indicate link degradation, not random bit flips)

**Anti-pattern:** Skipping CRC validation to "save CPU" when deep water multipath corruption is real scenario.

---

## Pattern 8: Operator Timeout & Autonomy

**Do:**
- Implement 5-min operator timeout (if no Firebase command, execute homing)
- Define homing route during preflight (waypoint from dive start location)
- Test timeout logic in simulation with mock Firebase
- Log every autonomy decision to SQLite buffer

**Don't:**
- Wait indefinitely for operator (deadlock scenario)
- Assume homing always succeeds (may surface in danger zone, requires operator abort)
- Skip pre-dive homing route validation (must verify path is safe)

**Anti-pattern:** Robot executes autonomous homing into rock formation because nobody validated route safety in preflight.

---

## Pattern 9: Cold Start & Battery Sag

**Do:**
- Check battery voltage >11V in preflight (prevents brownout)
- Measure voltage before and after thruster spin test
- Apply 0.5V sag margin (assume worst case)
- Log battery voltage trend across mission

**Don't:**
- Start dive with battery <20% (insufficient margin for emergency surface)
- Assume battery voltage is linear (real batteries have discharge curve kink near 0%)

**Anti-pattern:** Robot dies at 15% battery when it said 20% (voltage dropped 0.8V over 2 min due to thruster surge).

---

## References

- FSM state machine: `robotics/autonomous_agent_main.py` (OperationalPhase enum)
- PID tuning: `docs/THRUSTER_SPECIFICATION_TEMPLATE.md` (Ziegler-Nichols worked example)
- Telemetry protocol: `robotics/protocol/robot_data.proto` + `protobuf_serializer.py`
- Autonomy logic: `robotics/autonomy_engine/self_aware_agent.py`
- Operational procedures: `docs/OPERATIONAL_STANDARDS_99.md` (33 preflight, 33 diving, 33 crisis)

