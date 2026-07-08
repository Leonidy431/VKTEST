# Hardware Platform Selection Guide: BlueROV2 vs Industrial Alternatives

**Date:** 2026-07-08  
**Context:** Choosing between open-source modular vs closed proprietary ROV platforms  
**Decision Impact:** Affects your 18-month roadmap and architectural flexibility  

---

## Executive Summary

**TL;DR:** Use **BlueROV2 Heavy Frame + Jetson Orin Nano + T500 Thrusters + Acoustic Sonar**

This gives you:
- ✅ Open-source architecture (no vendor lockdown)
- ✅ Enough compute for real-time sonar processing
- ✅ Modular expansion (add manipulator, additional cameras, etc.)
- ✅ Our Firebase/WebRTC integration works natively
- ✅ $2-3K total cost vs $8-15K for industrial alternatives

---

## 1. Platform Comparison Matrix (12 Parameters)

| Parameter | BlueROV2 Standard | BlueROV2 Heavy | FIFISH V6 Plus | Chasing M2 Pro | Recommendation |
|---|---|---|---|---|---|
| **Open Source** | ✅ Full | ✅ Full | ❌ Closed | ❌ Closed | BlueROV2 |
| **Root SSH Access** | ✅ Yes (Debian) | ✅ Yes (Debian) | ⚠️ Limited | ❌ No | BlueROV2 |
| **Payload Capacity** | 2-3 kg | 5-8 kg | 1-2 kg | 2-4 kg | BlueROV2 Heavy |
| **ROS2/DDS Support** | ✅ Native | ✅ Native | ❌ Proprietary API | ❌ Proprietary API | BlueROV2 |
| **Custom Firmware** | ✅ ArduSub | ✅ ArduSub | ❌ Locked | ❌ Locked | BlueROV2 |
| **Thruster Swap** | ✅ Easy (tool-less) | ✅ Easy (tool-less) | ❌ Requires disassembly | ❌ Requires disassembly | BlueROV2 |
| **Firebase/MQTT** | ✅ (our code) | ✅ (our code) | ⚠️ Via SDK only | ⚠️ Via SDK only | BlueROV2 |
| **Sonar Integration** | ✅ ping360 native | ✅ ping360 native | ⚠️ Proprietary sonar only | ⚠️ Proprietary sonar only | BlueROV2 |
| **Max Depth** | 300 m | 300 m | 500 m | 300 m | Industrial (if needed) |
| **Speed/Agility** | 1.5 m/s | 1.2 m/s | 2.5 m/s | 1.8 m/s | Industrial (fast surveys) |
| **Battery Life** | 4-5 hours | 3-4 hours | 4-6 hours | 5-7 hours | Industrial (extended ops) |
| **Total Cost** | $2,500 | $3,200 | $8,000 | $12,000 | BlueROV2 |

---

## 2. The Proprietary Lockdown Problem

### Why Chinese Industrial Systems Are "Closed"

**Example: Chasing M2 Pro**

```
Your Architecture:
┌─────────────────────────────────────────┐
│ Your Firebase/WebRTC Control Plane      │
│ (runs your autonomous decision tree)    │
└────────────────────┬────────────────────┘
                     │
        ┌────────────▼──────────────┐
        │ Your Binary Telemetry     │
        │ (Protobuf + Sequence ID)  │
        └────────────┬──────────────┘
                     │
                     ▼
        ❌ BLOCKED: Chasing M2 only accepts
           their proprietary protocol
           
        💬 "You can SEND commands via our SDK,
            but you can't receive raw sonar data
            or telemetry in your format"
```

### What Gets Locked Down

| Component | BlueROV2 | Chasing/FIFISH |
|---|---|---|
| **Motor Protocol** | UART + MAVLink | Proprietary binary |
| **Sonar Data** | Raw bytes (your code) | Processed via their cloud |
| **Camera Stream** | Raw H.264 (WebRTC) | Compressed, filtered |
| **Depth/Pressure** | Raw I2C sensor | Sensor fusion (black box) |
| **Battery State** | Raw ADC values | Filtered + estimated |
| **Firmware Updates** | `git pull && ./deploy.sh` | "Update via app" (60 MB) |

**Result:** Your PointPillars neural network on Pixel 10 can't process raw sonar → defeats purpose of our dual-channel architecture.

---

## 3. "Guru Assembly" Strategy (Recommended)

### The Hybrid Approach

Build your own "Industrial-Grade BlueROV2":

```
FRAME:          BlueROV2 Heavy (8 thrusters = better stability)
                ↓
THRUSTERS:      2× T500 (vertical)
                4× T200 (horizontal)
                = 250+ N total thrust (vs 80 N standard)
                ↓
COMPUTE:        Jetson Orin Nano (12 TFLOPS vs Pi 4's 15 GFLOPS)
                Run PointPillars NN @ 20 FPS locally
                ↓
PAYLOAD BAY:    Acoustic sonar (ping360 or Ping360+)
                3D camera (Zed 2i)
                Battery monitor
                ↓
COMMUNICATION:  Our Firebase/WebRTC architecture
                (Pi as edge controller, Jetson as compute)
                ↓
POWER:          48V LiFePO4 battery pack (vs 18V standard)
                → 200+ minutes endurance
```

### Cost Breakdown

```
BlueROV2 Heavy Frame:       $2,200
├─ includes: 8 basic thrusters, frame, tether
│
T500 Thrusters (2×):        $400 (upgrade from basic)
T200 Thrusters (4×):        $800 (upgrade from basic)
├─ Total thruster upgrade:  +$1,200
│
Jetson Orin Nano (8GB):     $250
├─ vs Raspberry Pi 5: $80 (but 80× more compute)
│
Acoustic Sonar (ping360+):  $3,000
├─ vs $1,200 for basic ping360
│
3D Camera (Zed 2i):         $500
├─ Depth + RGB + IMU
│
Battery Pack (LiFePO4):     $400
├─ 48V 10Ah = 480Wh
│
Miscellaneous (cables, etc): $250
│
═══════════════════════════════════════
TOTAL: ~$7,600 (still 50% cheaper than Chasing M2)
```

**BUT:** Gives you:
- ✅ Full control over firmware + protocol
- ✅ Real-time sonar processing (8 TFLOPS)
- ✅ Our Firebase/WebRTC architecture works natively
- ✅ Can deploy PointPillars NN locally
- ✅ Open community + documentation

---

## 4. Compute Platform Decision: Pi vs Jetson

### Your Sensing Priority Determines Everything

**Decision Tree:**

```
┌─ What's your primary mission?
│
├─ Acoustic Sonar ONLY (ping360)
│  └─ Data rate: 40 KB/sec (low)
│     Processing: Simple beamforming
│     → Raspberry Pi 4/5 SUFFICIENT
│     → Cost: $80-120
│
├─ Acoustic + Basic 3D Camera
│  └─ Data rate: 200 KB/sec (medium)
│     Processing: Image processing + sonar fusion
│     → Raspberry Pi 5 MARGINAL
│     → Cost: $120
│
├─ Acoustic + Stereo 3D Camera + PointPillars NN
│  └─ Data rate: 500 KB/sec (high)
│     Processing: Real-time 3D reconstruction
│     → Jetson Orin Nano REQUIRED
│     → Cost: $250
│
└─ Multi-sensor (sonar + 2× cameras + thermal + lidar)
   └─ Data rate: 2+ MB/sec (very high)
      Processing: Sensor fusion + real-time NN
      → Jetson Orin (or Jetson AGX) REQUIRED
      → Cost: $250-800
```

---

## 5. Three Sensing Scenarios

### Scenario A: Acoustic Sonar Only (Your Current Plan)

**Hardware:**
```
Sensor:    Blue Robotics ping360 Scanning Sonar
Output:    1,200 samples/sec @ 16-bit = 2.4 KB/sec
Format:    Raw I2C frames (no processing)

On Pixel 10:
- Receive via WebRTC (raw sonar)
- Run beamforming in PointPillars NN
- Display 3D point cloud

Compute Needed: Pi 5 ✅ SUFFICIENT
  - Real-time beamforming: ~10 GFLOPS
  - Pi 5 available: 15 GFLOPS
  - Margin: 5 GFLOPS (good)
```

**Cost:** BlueROV2 Heavy + Pi 5 + ping360 = **$4,500**

---

### Scenario B: Stereo 3D Vision + Acoustic (Research Quality)

**Hardware:**
```
Sensors:   ping360 + ZED 2i Stereo Camera
Outputs:   
  - Sonar: 2.4 KB/sec
  - Camera: 1280×720×30fps RGB = 27 MB/sec!

Processing on Robot:
  Step 1: Receive stereo frames (GPU decode H.264)
  Step 2: Run stereo depth estimation (CUDA)
  Step 3: Fuse sonar + depth map
  Step 4: Run PointPillars NN (15 TFLOPS)
  Step 5: Send compressed 3D cloud (200 KB/sec)

Compute Needed: Jetson Orin Nano ✅ REQUIRED
  - Stereo decode + NN: 40 GFLOPS
  - Orin available: 40 GFLOPS at FP8
  - Margin: None (at capacity)
```

**Cost:** BlueROV2 Heavy + Jetson Orin + ping360 + ZED 2i = **$6,200**

---

### Scenario C: Multi-Modal Deep Sea Reconnaissance (Professional)

**Hardware:**
```
Sensors:   ping360 + ZED 2i + Thermal + Leak Detector
Output:    40+ MB/sec uncompressed

Real-time Processing:
  - Stereo 3D reconstruction (structure-from-motion)
  - Thermal anomaly detection
  - Autonomous obstacle avoidance
  - Neural network inference (YOLOv8 for objects)
  - Sensor fusion (Kalman filter)

Compute Needed: Jetson Orin (full, 275 TFLOPS)
  - Professional-grade deep learning
  - Multi-stream processing
  - No frame drops
```

**Cost:** BlueROV2 Heavy + Jetson Orin + all sensors = **$12,000**
(Comparable to Chasing M2 Pro, but WITH full control)

---

## 6. Our Architecture Mapping to Hardware

### How Your Firebase/WebRTC Design Fits Each Platform

#### Option 1: BlueROV2 Standard + Pi 5 (Acoustic Only)

```
Control Plane:
  Pixel 10 → Firebase → Pi 5
  (commands: "dive_to_20m", "scan_here")

Data Plane:
  Pi 5 → WebRTC UDP → Pixel 10
  (sonar: 40 KB/sec raw)

Processing:
  Pi 5: Buffer sonar locally, send aggregated every 1 sec
  Pixel 10: Full PointPillars NN (GPU inference)

Bottleneck: None (well-balanced)
Latency: 100-200 ms (acceptable)
Cost: $3,500 total
```

✅ **RECOMMENDED if:** Acoustic sonar is your PRIMARY sensor

---

#### Option 2: BlueROV2 Heavy + Jetson Orin Nano (Full 3D)

```
Control Plane:
  Pixel 10 → Firebase → Jetson Orin
  (commands: same)

Data Plane:
  Jetson Orin → WebRTC UDP → Pixel 10
  (sonar + stereo: 200-300 KB/sec)

Processing:
  Jetson Orin: Real-time 3D reconstruction locally
  ├─ Stereo depth estimation (CUDA)
  ├─ Sonar beamforming (CUDA)
  ├─ Sensor fusion (500 GFLOP Kalman filter)
  └─ PointPillars NN (FP8 quantized)
  
  Pixel 10: Visualization only (no compute burden)

Bottleneck: WebRTC stream quality (depends on tether/mmWave)
Latency: 50-100 ms (very responsive)
Cost: $6,200 total
```

✅ **RECOMMENDED if:** You need 3D reconstruction + autonomous navigation

---

#### Option 3: Chasing M2 Pro (DON'T DO THIS for your use case)

```
Control Plane:
  Pixel 10 → Chasing Cloud API → M2 Pro
  (commands: via their SDK, 200ms latency)

Data Plane:
  M2 Pro → Chasing Cloud → Pixel 10
  (pre-processed video, 500ms latency)

Processing:
  M2 Pro: Proprietary (you can't change it)
  Chasing Cloud: They decide what you receive
  Pixel 10: Display what they send you

Problems:
  ❌ Can't receive raw sonar
  ❌ Our WebRTC doesn't work
  ❌ Firebase/MQTT can't integrate
  ❌ Latency too high for real-time control
  ❌ Locked into their ecosystem

Cost: $12,000 + subscription
```

❌ **NOT RECOMMENDED** (breaks your architecture)

---

## 7. Quick Decision Framework

Answer these 3 questions:

**Q1: What sensor is CRITICAL for your mission?**
```
A: "Just need acoustic sonar to detect objects"
   → BlueROV2 + Pi 5 ✅

B: "Need 3D reconstruction + object tracking"
   → BlueROV2 Heavy + Jetson Orin ✅

C: "Need AI inference on raw sensor data in real-time"
   → BlueROV2 Heavy + Jetson Orin ✅
```

**Q2: How much raw data per second?**
```
A: < 100 KB/sec
   → Raspberry Pi 5 sufficient

B: 100-500 KB/sec
   → Jetson Orin Nano required

C: > 500 KB/sec
   → Jetson Orin (full) required
```

**Q3: Do you need to modify firmware/protocol?**
```
A: "Yes, I need full control"
   → BlueROV2 (open) ✅

B: "No, I'm OK with vendor API"
   → Chinese alternative acceptable

C: "I don't know yet"
   → BlueROV2 (you can always simplify later)
```

---

## 8. Recommended Stack for YOUR System

### Based on Our Architecture (Firebase + WebRTC + Protobuf)

**PRIMARY RECOMMENDATION:**

```
Platform:       BlueROV2 Heavy Configuration
├─ Frame:       BlueROV2 HD with 8 thrusters
├─ Thrusters:   2× T500 (vertical) + 4× T200 (horizontal)
├─ Tether:      150 m Fathom-X (10 Gbps fiber if needed)
├─ Compute:     Raspberry Pi 5 (8GB model)
│               + Jetson Orin Nano (in secondary bay, optional)
├─ Sensors:     
│   ├─ Depth: BMP390 (already in our design)
│   ├─ Sonar: Blue Robotics ping360 (2D scanning)
│   ├─ Camera: HD USB camera (for operator monitoring)
│   ├─ IMU: MPU6050 (already in our design)
│   └─ GPS: u-blox (surface positioning)
├─ Power:       48V LiFePO4 200Wh (6-7 hour endurance)
├─ Software:    
│   ├─ Core: ArduSub (open-source firmware)
│   ├─ Edge: Our AutonomousAgent (Docker)
│   ├─ Control: Firebase Realtime DB
│   ├─ Data: WebRTC P2P streaming
│   └─ Fallback: MQTT QoS 2
└─ Total Cost:  $5,500-6,000

Deployment Timeline: 6 weeks (hardware + integration)
Operator Interface: Pixel 10 Pro XL (Foreground Service)
Mission Endurance: 200+ minutes @ 1 m/s
Sensing Capability: 3D sonar mapping + stereo optional
```

---

## 9. Integration Path: ArduSub → Our Architecture

### How BlueROV2 (ArduSub firmware) talks to our system

```
BlueROV2 (ArduSub firmware)
  ↓ MAVLink protocol
Raspberry Pi 5 (ArduPilot companion)
  ↓ Via UART
Docker Container (Our AutonomousAgent)
  ├─ Read: depth, attitude, battery via MAVLink
  ├─ Decide: FSM logic (DIVING, SURFACE_IDLE, etc)
  ├─ Buffer: SQLite local persistence
  ├─ Send: Protobuf-encoded telemetry
  │        via Firebase (control plane)
  │        via WebRTC (data plane)
  └─ Receive: Operator commands from Pixel 10

Pixel 10 Pro XL
  ├─ Foreground Service (keeps app alive)
  ├─ Firebase SDK (receives events)
  ├─ FCM (push notifications)
  ├─ WebRTC P2P (receives sonar stream)
  ├─ PointPillars NN (processes 3D cloud)
  └─ Dashboard UI (depth graph + map + button)
```

**Implementation:** MAVLink bridge between ArduSub ↔ Our AutonomousAgent

```python
# In Docker container on Pi 5
from pymavlink.dialects.v10 import ardupilotmega as mavlink

# Connect to ArduSub's MAVLink endpoint
connection = mavlink.MAVConnection('udpin:127.0.0.1:14550')

# Listen for heartbeat + sensor data
msg = connection.recv_msg()
if msg.get_type() == 'HEARTBEAT':
    autonomy_engine.update_robot_state(msg.system_status)
elif msg.get_type() == 'SCALED_PRESSURE':
    autonomy_engine.update_depth(msg.press_abs)
elif msg.get_type() == 'ATTITUDE':
    autonomy_engine.update_orientation(msg.roll, msg.pitch, msg.yaw)

# Send commands back to ArduSub
autonomy_engine.control_thrusters(forward, lateral, vertical)
connection.mav.rc_channels_override_send(1, ch1, ch2, ch3, ch4, 0, 0, 0, 0)
```

---

## 10. The Final Answer

### For Your Specific Question:

**"What type of sensing is your priority?"**

#### If ACOUSTIC SONAR (most likely):
```
Use: BlueROV2 Standard + Raspberry Pi 5 + ping360
Cost: $3,500
Data rate: 40 KB/sec
Processing: Beamforming on Pixel 10
Timeline: 4 weeks to deploy
✅ Our architecture works perfectly
```

#### If STEREO 3D + SONAR (research):
```
Use: BlueROV2 Heavy + Jetson Orin Nano + ping360 + ZED 2i
Cost: $6,200
Data rate: 200 KB/sec
Processing: Real-time 3D reconstruction
Timeline: 6 weeks to deploy
✅ Our architecture works better (Jetson has room for inference)
```

#### If MULTI-SENSOR (professional):
```
Use: BlueROV2 Heavy + Jetson Orin (full) + all sensors
Cost: $12,000
Data rate: 500+ KB/sec
Processing: Sensor fusion + multiple NNs
Timeline: 8 weeks to deploy
✅ Our architecture scales well (but overkill for acoustic only)
```

---

## Conclusion: Don't Buy Chinese Closed Systems

**The Hidden Cost of Proprietary Lockdown:**

| Hidden Costs | Chasing M2 Pro | Your BlueROV2 |
|---|---|---|
| SDK integration time | 4 weeks | Included (MAVLink) |
| Data format conversion | 2 weeks | None (raw access) |
| Firmware modification | ❌ Impossible | ✅ `git push` |
| Sonar processing | ❌ Cloud-dependent | ✅ Local GPU (Jetson) |
| Custom sensors | ❌ Proprietary connector | ✅ Any I2C/SPI sensor |
| **True Total Cost** | **$20,000+** | **$6,000** |

---

**RECOMMENDATION:** Order **BlueROV2 Heavy** frame + **T500 thrusters** + **Raspberry Pi 5** today.

Add **Jetson Orin Nano** in Phase 2 if sonar processing needs it.

You'll be in water in 6 weeks with full architectural control. ✅

