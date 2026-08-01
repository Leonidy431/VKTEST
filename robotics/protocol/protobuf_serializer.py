"""
Protocol Buffers Serialization with Integrity Checking

Implements binary telemetry encoding with:
- Sequence ID tracking (detect out-of-order packets)
- CRC32 integrity checking
- Firebase hex encoding for safe transport
- ACK protocol for command delivery guarantee
"""

import struct
import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
import zlib


class MessageType(Enum):
    TELEMETRY = 1
    COMMAND = 2
    ACK = 3
    EVENT = 4
    HOMING = 5


@dataclass
class GpsCoordinates:
    latitude: float
    longitude: float
    accuracy_meters: int = 0

    def to_bytes(self) -> bytes:
        return struct.pack('<ddi', self.latitude, self.longitude, self.accuracy_meters)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'GpsCoordinates':
        lat, lon, acc = struct.unpack('<ddi', data)
        return cls(lat, lon, acc)


@dataclass
class SensorData:
    depth_m: float
    temperature_c: float
    salinity_ppt: float
    battery_pct: int
    signal_quality_pct: int
    heading_degrees: int
    velocity_ms: float

    def to_bytes(self) -> bytes:
        return struct.pack(
            '<ffffBBf',
            self.depth_m,
            self.temperature_c,
            self.salinity_ppt,
            self.battery_pct,
            self.signal_quality_pct,
            self.heading_degrees,
            self.velocity_ms
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SensorData':
        depth, temp, salinity, battery, signal, heading, velocity = struct.unpack(
            '<ffffBBf', data
        )
        return cls(depth, temp, salinity, battery, signal, heading, velocity)


class TelemetryMessage:
    """Telemetry message (Robot → Operator)."""

    def __init__(self,
                 sequence_id: int,
                 robot_id: str,
                 message_type: str,
                 gps: GpsCoordinates,
                 sensors: SensorData,
                 current_state: str,
                 queue_depth: int = 0):
        self.sequence_id = sequence_id
        self.timestamp_unix_ms = int(time.time() * 1000)
        self.robot_id = robot_id
        self.message_type = message_type
        self.gps = gps
        self.sensors = sensors
        self.current_state = current_state
        self.queue_depth = queue_depth
        self.crc32 = 0

    def pack(self) -> bytes:
        """Pack to binary format."""
        # Build message without CRC
        msg = struct.pack(
            '<I Q H',
            self.sequence_id,
            self.timestamp_unix_ms,
            len(self.robot_id.encode())
        )
        msg += self.robot_id.encode()
        msg += struct.pack('H', len(self.message_type.encode()))
        msg += self.message_type.encode()
        msg += self.gps.to_bytes()
        msg += self.sensors.to_bytes()
        msg += struct.pack('H', len(self.current_state.encode()))
        msg += self.current_state.encode()
        msg += struct.pack('<I', self.queue_depth)

        # Calculate CRC32 over all data
        self.crc32 = zlib.crc32(msg) & 0xffffffff

        # Append CRC32
        msg += struct.pack('<I', self.crc32)

        return msg

    def pack_hex(self) -> str:
        """Pack to hex string for Firebase transport."""
        return self.pack().hex()

    @classmethod
    def unpack(cls, data: bytes) -> 'TelemetryMessage':
        """Unpack from binary format."""
        offset = 0

        # Header
        seq_id, timestamp, robot_len = struct.unpack_from('<I Q H', data, offset)
        offset += 14
        robot_id = data[offset:offset + robot_len].decode()
        offset += robot_len

        msg_type_len = struct.unpack_from('H', data, offset)[0]
        offset += 2
        msg_type = data[offset:offset + msg_type_len].decode()
        offset += msg_type_len

        # GPS
        gps_data = data[offset:offset + 24]
        offset += 24
        gps = GpsCoordinates.from_bytes(gps_data)

        # Sensors
        sensor_data = data[offset:offset + 23]
        offset += 23
        sensors = SensorData.from_bytes(sensor_data)

        # State
        state_len = struct.unpack_from('H', data, offset)[0]
        offset += 2
        current_state = data[offset:offset + state_len].decode()
        offset += state_len

        # Queue depth
        queue_depth = struct.unpack_from('<I', data, offset)[0]
        offset += 4

        # CRC32
        crc32_stored = struct.unpack_from('<I', data, offset)[0]

        # Verify CRC
        msg_data = data[:offset]
        crc32_calc = zlib.crc32(msg_data) & 0xffffffff

        msg = cls(seq_id, robot_id, msg_type, gps, sensors, current_state, queue_depth)
        msg.crc32 = crc32_stored
        msg.timestamp_unix_ms = timestamp

        if crc32_calc != crc32_stored:
            raise ValueError(
                f"CRC32 mismatch: expected {crc32_stored:08x}, got {crc32_calc:08x}"
            )

        return msg

    @classmethod
    def unpack_hex(cls, hex_string: str) -> 'TelemetryMessage':
        """Unpack from hex string."""
        return cls.unpack(bytes.fromhex(hex_string))


class CommandMessage:
    """Command message (Operator → Robot)."""

    def __init__(self,
                 command_id: int,
                 robot_id: str,
                 command_type: str,
                 parameters: Dict[str, str],
                 priority: int = 1,
                 timeout_sec: int = 300):
        self.command_id = command_id
        self.timestamp_unix_ms = int(time.time() * 1000)
        self.robot_id = robot_id
        self.command_type = command_type
        self.parameters = parameters
        self.priority = priority
        self.timeout_sec = timeout_sec
        self.crc32 = 0

    def pack(self) -> bytes:
        """Pack to binary format."""
        msg = struct.pack(
            '<I Q H',
            self.command_id,
            self.timestamp_unix_ms,
            len(self.robot_id.encode())
        )
        msg += self.robot_id.encode()
        msg += struct.pack('H', len(self.command_type.encode()))
        msg += self.command_type.encode()

        # Parameters (as serialized key=value pairs)
        params_str = '&'.join([f"{k}={v}" for k, v in self.parameters.items()])
        msg += struct.pack('H', len(params_str.encode()))
        msg += params_str.encode()

        msg += struct.pack('<BB I', self.priority, 0, self.timeout_sec)

        # CRC32
        self.crc32 = zlib.crc32(msg) & 0xffffffff
        msg += struct.pack('<I', self.crc32)

        return msg

    def pack_hex(self) -> str:
        """Pack to hex string for Firebase transport."""
        return self.pack().hex()

    @classmethod
    def unpack_hex(cls, hex_string: str) -> 'CommandMessage':
        """Unpack from hex string."""
        data = bytes.fromhex(hex_string)
        offset = 0

        cmd_id, timestamp, robot_len = struct.unpack_from('<I Q H', data, offset)
        offset += 14
        robot_id = data[offset:offset + robot_len].decode()
        offset += robot_len

        cmd_type_len = struct.unpack_from('H', data, offset)[0]
        offset += 2
        command_type = data[offset:offset + cmd_type_len].decode()
        offset += cmd_type_len

        params_len = struct.unpack_from('H', data, offset)[0]
        offset += 2
        params_str = data[offset:offset + params_len].decode()
        offset += params_len

        parameters = {}
        if params_str:
            for pair in params_str.split('&'):
                k, v = pair.split('=', 1)
                parameters[k] = v

        priority, _, timeout = struct.unpack_from('<BB I', data, offset)
        offset += 6

        crc32_stored = struct.unpack_from('<I', data, offset)[0]

        msg = cls(cmd_id, robot_id, command_type, parameters, priority, timeout)
        msg.timestamp_unix_ms = timestamp
        msg.crc32 = crc32_stored

        return msg


class CommandAck:
    """ACK message (Robot → Operator: Command acknowledgment)."""

    def __init__(self,
                 command_id: int,
                 robot_id: str,
                 accepted: bool,
                 execution_status: str = "QUEUED",
                 execution_progress_pct: int = 0,
                 reject_reason: str = ""):
        self.command_id = command_id
        self.received_timestamp_unix_ms = int(time.time() * 1000)
        self.robot_id = robot_id
        self.accepted = accepted
        self.reject_reason = reject_reason
        self.execution_status = execution_status
        self.execution_progress_pct = execution_progress_pct
        self.crc32 = 0

    def pack(self) -> bytes:
        """Pack to binary format."""
        msg = struct.pack(
            '<I Q H',
            self.command_id,
            self.received_timestamp_unix_ms,
            len(self.robot_id.encode())
        )
        msg += self.robot_id.encode()
        msg += struct.pack('B', 1 if self.accepted else 0)
        msg += struct.pack('H', len(self.reject_reason.encode()))
        msg += self.reject_reason.encode()
        msg += struct.pack('H', len(self.execution_status.encode()))
        msg += self.execution_status.encode()
        msg += struct.pack('B', self.execution_progress_pct)

        # CRC32
        self.crc32 = zlib.crc32(msg) & 0xffffffff
        msg += struct.pack('<I', self.crc32)

        return msg

    def pack_hex(self) -> str:
        """Pack to hex string for Firebase transport."""
        return self.pack().hex()


class HomingInitiated:
    """Homing fallback message (Robot → Operator: Autonomous recovery)."""

    def __init__(self,
                 sequence_id: int,
                 robot_id: str,
                 reason: str,
                 estimated_return_time_sec: int,
                 last_known_position: GpsCoordinates,
                 battery_pct: int,
                 strategy: str = "DIRECT_ASCENT"):
        self.sequence_id = sequence_id
        self.timestamp_unix_ms = int(time.time() * 1000)
        self.robot_id = robot_id
        self.reason = reason
        self.estimated_return_time_sec = estimated_return_time_sec
        self.last_known_position = last_known_position
        self.battery_pct = battery_pct
        self.strategy = strategy
        self.crc32 = 0

    def pack(self) -> bytes:
        """Pack to binary format."""
        msg = struct.pack(
            '<I Q H',
            self.sequence_id,
            self.timestamp_unix_ms,
            len(self.robot_id.encode())
        )
        msg += self.robot_id.encode()
        msg += struct.pack('H', len(self.reason.encode()))
        msg += self.reason.encode()
        msg += struct.pack('<I', self.estimated_return_time_sec)
        msg += self.last_known_position.to_bytes()
        msg += struct.pack('B', self.battery_pct)
        msg += struct.pack('H', len(self.strategy.encode()))
        msg += self.strategy.encode()

        # CRC32
        self.crc32 = zlib.crc32(msg) & 0xffffffff
        msg += struct.pack('<I', self.crc32)

        return msg

    def pack_hex(self) -> str:
        """Pack to hex string for Firebase transport."""
        return self.pack().hex()


class ProtobufSerializer:
    """High-level serializer managing sequences and integrity."""

    def __init__(self, robot_id: str, logger: logging.Logger = None):
        self.robot_id = robot_id
        self.sequence_id = 0
        self.command_sequence = 0
        self.logger = logger or logging.getLogger(__name__)

    def next_sequence_id(self) -> int:
        """Get next sequence ID (0-4294967295, wraps around)."""
        self.sequence_id = (self.sequence_id + 1) & 0xffffffff
        return self.sequence_id

    def create_telemetry(self,
                        message_type: str,
                        gps: GpsCoordinates,
                        sensors: SensorData,
                        current_state: str,
                        queue_depth: int = 0) -> TelemetryMessage:
        """Create and return telemetry message."""
        seq = self.next_sequence_id()
        return TelemetryMessage(seq, self.robot_id, message_type, gps, sensors, current_state, queue_depth)

    def create_command_ack(self,
                          command_id: int,
                          accepted: bool,
                          execution_status: str = "QUEUED",
                          reject_reason: str = "") -> CommandAck:
        """Create and return ACK message."""
        return CommandAck(
            command_id,
            self.robot_id,
            accepted,
            execution_status,
            reject_reason=reject_reason
        )

    def create_homing_initiated(self,
                               reason: str,
                               estimated_return_time_sec: int,
                               last_known_position: GpsCoordinates,
                               battery_pct: int,
                               strategy: str = "DIRECT_ASCENT") -> HomingInitiated:
        """Create and return homing message."""
        seq = self.next_sequence_id()
        return HomingInitiated(seq, self.robot_id, reason, estimated_return_time_sec,
                             last_known_position, battery_pct, strategy)

    def log_sequence_gap(self, expected: int, received: int):
        """Log out-of-order packet detection."""
        gap = (received - expected) & 0xffffffff
        if gap > 0:
            self.logger.warning(
                f"Sequence gap detected: expected {expected}, received {received} (gap={gap})"
            )
