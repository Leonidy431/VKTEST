"""
Motor Control Module: PID Depth Stabilization

Exports:
- PIDDepthController: Main depth hold controller
- DepthSensor, MockDepthSensor: Pressure/depth sensing
- ThrusterDriver, MockThrusterDriver: Motor control
- PIDGains: Tuning parameters
"""

from .pid_depth_controller import (
    PIDDepthController,
    DepthSensor,
    MockDepthSensor,
    ThrusterDriver,
    MockThrusterDriver,
    PIDGains,
    DepthSensorCalibration,
    ThrusterMode,
)

__all__ = [
    "PIDDepthController",
    "DepthSensor",
    "MockDepthSensor",
    "ThrusterDriver",
    "MockThrusterDriver",
    "PIDGains",
    "DepthSensorCalibration",
    "ThrusterMode",
]
