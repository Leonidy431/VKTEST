# TI IWR6843 mmWave Robotics Stack — Quick Start

Complete integration guide for deploying TI IWR6843ISK-ODS radar with ROS2, PointPillars 3D detection, Nav2 navigation, and OctoMap SLAM.

---

## 0. Hardware Requirements

### Minimal Setup (< $400)
- **TI IWR6843ISK-ODS EVM board** — $250
- **Xilinx Platform Cable (JTAG)** — $50 (included with board)
- **USB-to-UART adapter** — $20
- **Micro USB power** — $5
- **Ubuntu 22.04 LTS machine** (x86_64 or ARM64) — Free
- **ROS2 Humble or Jazzy** — Free

### Recommended Robot Platform
- **Clearpath Warthog** (if available)
- **TurtleBot 4** (affordable alternative)
- **Custom wheeled robot** with:
  - Ubuntu 22.04 SBC (Jetson Orin, NUC, etc.)
  - URDF model for robot geometry
  - Motor controllers via ROS2

---

## 1. Environment Setup (30 min)

### 1.1 Install ROS2 Humble

```bash
# Add ROS2 GPG key
sudo curl -sSL https://repo.ros2.org/ros.key | sudo apt-key add -

# Add ROS2 repository
sudo sh -c 'echo "deb [arch=$(dpkg --print-architecture)] http://packages.ros2.org/ubuntu $(lsb_release -cs) main" > /etc/apt/sources.list.d/ros2-latest.list'

# Update and install
sudo apt update
sudo apt install ros-humble-desktop
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 1.2 Install Dependencies

```bash
# Core tools
sudo apt install -y \
  build-essential \
  cmake \
  git \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-pip

# PCL and 3D processing
sudo apt install -y \
  ros-humble-pcl-ros \
  ros-humble-pcl-conversions \
  ros-humble-perception-pcl \
  libpcl-dev

# Navigation
sudo apt install -y \
  ros-humble-navigation2 \
  ros-humble-nav2-bringup \
  ros-humble-cartographer \
  ros-humble-cartographer-ros

# SLAM
sudo apt install -y \
  ros-humble-octomap-msgs \
  ros-humble-octomap-ros \
  liboctomap-dev

# Additional
sudo apt install -y \
  ros-humble-tf2-ros \
  ros-humble-tf2-geometry-msgs \
  ros-humble-laser-geometry \
  ros-humble-pointcloud-to-laserscan
```

### 1.3 Create ROS2 Workspace

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws

# Clone the phased array robotics project
git clone https://github.com/leonidy431/vktest.git src/vktest
cd src/vktest

# Setup the mmWave driver package
mkdir -p ti_mmwave_robotics
cp robotics/ti_mmwave_ros2_setup/* ti_mmwave_robotics/

# Return to workspace
cd ~/ros2_ws

# Install dependencies
rosdep install -i --from-path src --rosdistro humble -y

# Build
colcon build --symlink-install --parallel-workers 4
```

---

## 2. Hardware Setup (45 min)

### 2.1 Physical Assembly

1. **Unbox TI IWR6843ISK-ODS board**
   - Remove from anti-static bag
   - Verify 4 ceramic antennas are present (120° pattern)
   - Inspect for damage

2. **Mount to robot**
   ```
   Robot Front (Forward Direction)
         ↓
   Radar Antennas
     ↑ ↑ ↑ ↑
    (4 elements in UPA)
   
   Height: ~50 cm above ground
   Orientation: 0° = forward direction of robot
   ```

3. **Connect power**
   - Micro USB → 5V power supply
   - OR UART header → external power (3.3V)

4. **Connect UART**
   - USB-to-UART adapter → TX/RX pins
   - Baud rate: 115,200
   - Device: `/dev/ttyUSB0` (or similar)

### 2.2 Firmware Flash

```bash
# Download TI mmWave SDK
wget https://www.ti.com/tool/download/MMWAVE-SDK-03-06-00-13

# Extract
unzip mmwave_sdk_03_06_00_13.zip
cd mmwave_sdk_03_06_00_13

# Connect board via JTAG, then flash
# (Detailed instructions in TI documentation)
# Alternatively, board comes pre-flashed for basic operation
```

### 2.3 Verify UART Communication

```bash
# Test connection
minicom -D /dev/ttyUSB0 -b 115200

# You should see periodic telemetry output from the board
# Ctrl-A Q to exit minicom

# Or use ROS2 UART diagnostic
ros2 run diagnostic_aggregator aggregator_node
```

---

## 3. ROS2 Nodes Startup (10 min)

### 3.1 Terminal 1: Core Driver

```bash
source ~/ros2_ws/install/setup.bash

# Launch only the IWR6843 driver
ros2 launch ti_mmwave_robotics ti_mmwave_driver.launch.py \
  uart_port:=/dev/ttyUSB0 \
  baud_rate:=115200

# Expected output:
# [ti_mmwave_driver-1] [INFO] Connecting to UART /dev/ttyUSB0
# [ti_mmwave_driver-1] [INFO] Publishing point cloud on /radar/pointcloud
# [ti_mmwave_driver-1] [INFO] Publishing 2D scan on /radar/scan_2d
# [ti_mmwave_driver-1] [INFO] Node running at 10 Hz
```

### 3.2 Terminal 2: Perception Stack

```bash
source ~/ros2_ws/install/setup.bash

# Launch full detection + SLAM + navigation
ros2 launch ti_mmwave_robotics ti_mmwave_full_stack.launch.py \
  enable_detector:=true \
  enable_slam:=true \
  enable_nav2:=true

# Monitor topics
ros2 topic list | grep -E "(radar|scan|object|octomap)"
```

### 3.3 Terminal 3: Visualization

```bash
# Start RViz2
rviz2 -d ~/ros2_ws/src/vktest/robotics/ti_mmwave_ros2_setup/config/radar_visualization.rviz

# Or configure manually:
# Add displays:
#   - PointCloud2: /radar/pointcloud (white points)
#   - LaserScan: /radar/scan_2d (green rays)
#   - MarkerArray: /radar/objects_3d (3D bounding boxes)
#   - OccupancyGrid: /map (2D map)
#   - TF: tree visualization
```

---

## 4. Verification Checklist (15 min)

### 4.1 Check Topics

```bash
# List active topics
ros2 topic list

# Expected topics:
# /radar/raw_pointcloud         (sensor_msgs/PointCloud2)
# /radar/scan_2d                (sensor_msgs/LaserScan)
# /radar/objects_3d             (visualization_msgs/MarkerArray)
# /radar/obstacles              (sensor_msgs/PointCloud2)
# /map                          (nav_msgs/OccupancyGrid)
# /tf                           (tf2_msgs/TFMessage)
# /amcl_pose                    (geometry_msgs/PoseWithCovarianceStamped)
# /odom                         (nav_msgs/Odometry)
```

### 4.2 Check Point Cloud Data

```bash
# Print a single point cloud message
ros2 topic echo /radar/raw_pointcloud --once

# Expected output:
# header:
#   frame_id: "radar"
#   seq: 42
# height: 1
# width: 256  (variable, depends on detections)
# fields:
#   - name: "x"
#     offset: 0
#     datatype: 7
#     count: 1
#   ... (y, z, intensity)
# data: <binary point data>
```

### 4.3 Check 2D Scan

```bash
# Print 2D laser scan (subset of 3D cloud)
ros2 topic echo /radar/scan_2d --once | head -20

# Expected:
# angle_min: -1.5707963...  (-90°)
# angle_max: 1.5707963...   (+90°)
# angle_increment: 0.0087...
# range_min: 0.5
# range_max: 50.0
# ranges: [50.0, 50.0, ..., 4.2, 3.8, ..., 50.0]
```

### 4.4 Check Object Detections

```bash
# Only if PointPillars is running
ros2 topic echo /radar/objects_3d --once

# Expected: Bounding boxes (visualization_msgs/Marker) around detected objects
```

### 4.5 Performance Metrics

```bash
# Monitor CPU/latency
ros2 run diagnostic_aggregator aggregator_node

# Check frame processing time
ros2 run tf2_ros tf_monitor radar base_link

# Typical performance:
# - Point cloud: 10 Hz (100ms per frame)
# - Detection: 5-10 Hz (100-200ms latency)
# - SLAM update: 1-2 Hz (500-1000ms mapping)
# - Nav2 planning: 1 Hz (1000ms replanning)
```

---

## 5. Troubleshooting

### Issue: No UART Connection
```bash
# Check device list
ls -la /dev/ttyUSB*

# Change permissions if needed
sudo usermod -a -G dialout $USER
newgrp dialout

# Try different baud rates
for br in 115200 230400 460800; do
  echo "Testing $br..."
  timeout 1 cat /dev/ttyUSB0 &
  stty -F /dev/ttyUSB0 $br raw
done
```

### Issue: Empty Point Cloud
- **Cause:** Antenna orientation wrong OR firmware needs update
- **Fix:** Verify all 4 antennas face forward, rotate if needed

### Issue: Noisy Detections
- **Cause:** Clutter from walls/ground not filtered
- **Fix:** Enable `ground_removal_enabled: true` in config, increase CFAR threshold

### Issue: SLAM Map Jumps
- **Cause:** Loop closure detection failing, poor heading estimation
- **Fix:** Reduce velocity, enable wheel odometry fusion, use IMU for heading

### Issue: High CPU Load
- **Cause:** Full PointPillars detection + OctoMap SLAM together
- **Fix:** Disable PointPillars (use basic obstacle detector), reduce OctoMap resolution to 0.1m

---

## 6. Integration with Phased Array Audio

Connect mmWave radar with voice communication:

```bash
# Terminal 4: Audio Streaming (from earlier phased_array module)
source ~/ros2_ws/install/setup.bash
cd ~/ros2_ws/src/vktest

# Run robot voice communication
ros2 run phased_array audio_streamer_node.py \
  --rf-module qorvo \
  --mode voip_standard

# Now robot can:
# 1. Detect obstacles via mmWave (60 GHz radar)
# 2. Stream voice via Wi-Fi (5.8 GHz, adaptive codec)
# 3. Navigate autonomously (Nav2 + OctoMap SLAM)
```

Dual-band system:
```
        Robot Controller
              |
        ______|______
       |             |
    60 GHz          5.8 GHz
   mmWave          Wi-Fi Link
   (Sensing)       (Voice/Video)
   
   - Obstacle    - Voice call
   - SLAM        - Video stream
   - Nav2        - Beamforming
```

---

## 7. Real-World Validation (2-4 weeks)

### Week 1: Indoor Testing
- [ ] Point cloud quality assessment
- [ ] SLAM mapping accuracy (compare to visual fiducials)
- [ ] Navigation to waypoints (0-10m distances)
- [ ] Voice latency measurement (< 150ms target)

### Week 2: Outdoor Testing
- [ ] Extended range validation (20-50m)
- [ ] Weather effects (rain, fog) on radar
- [ ] Multipath mitigation evaluation
- [ ] Codec adaptation under motion

### Week 3: Stress Testing
- [ ] 8+ hour continuous operation
- [ ] Extreme temperatures (-10 to +50°C)
- [ ] Multiple obstacles (crowds, vehicles)
- [ ] Voice quality under poor signal

### Week 4: Documentation & Optimization
- [ ] Calibration parameters finalized
- [ ] Parameter documentation
- [ ] Performance benchmarks published
- [ ] Production deployment guide

---

## 8. References

**Official Documentation:**
- [TI IWR6843 User Guide](https://www.ti.com/tool/MMWAVE-SDK)
- [ROS2 Humble Documentation](https://docs.ros.org/en/humble/)
- [Nav2 Complete Guide](https://navigation.ros.org/)

**Key Papers:**
- PointPillars: "Fast Encoders for Object Detection from Point Clouds" (CVPR 2019)
- "Millimeter Wave Radar for Autonomous Vehicles" (IEEE IV 2023)

**Community Resources:**
- [RadarML GitHub](https://github.com/RadarML)
- [TI mmWave Lab Community](https://e2e.ti.com/support/sensors-group/sensors/f/sensors-forum)
- [ROS Discourse - Radar Integration](https://discourse.ros.org/)

---

**Status:** Ready for deployment  
**Version:** 1.0  
**Last Updated:** 2026-07-08
