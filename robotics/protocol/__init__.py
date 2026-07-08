"""
Protocol Buffers Module: Binary Telemetry with Integrity Checking

Exports:
- TelemetryMessage: Robot → Operator telemetry
- CommandMessage: Operator → Robot commands
- CommandAck: Robot → Operator acknowledgments
- HomingInitiated: Robot → Operator homing notifications
- ProtobufSerializer: High-level serialization API
- GpsCoordinates, SensorData: Data structures
"""

from .protobuf_serializer import (
    TelemetryMessage,
    CommandMessage,
    CommandAck,
    HomingInitiated,
    ProtobufSerializer,
    GpsCoordinates,
    SensorData,
    MessageType,
)

__all__ = [
    "TelemetryMessage",
    "CommandMessage",
    "CommandAck",
    "HomingInitiated",
    "ProtobufSerializer",
    "GpsCoordinates",
    "SensorData",
    "MessageType",
]
