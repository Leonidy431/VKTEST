"""
Bandwidth-Optimized Data Prioritization Encoder

Problem: Limited channel capacity (LoRa 1 kbps, satellite uplink 2-5 kbps)
Solution: Adaptive data compression with priority tiers

Blind spot addressed: "Firebase Lag"
- Instead of sending 64 bytes/sec, compress to 11-16 bytes/sec
- Critical data (GPS, battery) sent first
- Science data (thermocline) deferred or sampled

Priority Queue:
  Tier 1 (Critical): Robot position (GPS) + timestamp
  Tier 2 (Safety): Battery voltage + system status
  Tier 3 (Science): Temperature profile + depth
  Tier 4 (Raw): Acoustic data (dropped if no bandwidth)
"""

import struct
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import IntEnum
import logging


class DataPriority(IntEnum):
    """Data priority levels (1 = highest)."""
    CRITICAL = 1  # GPS, timestamp, battery state
    SAFETY = 2    # Battery voltage, temp warnings, error codes
    SCIENCE = 3   # Temperature, salinity, depth trends
    TELEMETRY = 4  # Detailed sensor readings
    DEBUG = 5     # Logs, raw data (dropped first)


class BandwidthMode(IntEnum):
    """Network bandwidth state."""
    LUXE = 0       # >100 kbps (full data)
    NORMAL = 1     # 10-100 kbps (aggregated)
    CONSTRAINED = 2  # 1-10 kbps (LoRa, drops low priority)
    CRITICAL = 3   # <1 kbps (GPS + battery only)


@dataclass
class CompressedTelemetry:
    """Compressed data packet (fixed size for transmission)."""
    priority: DataPriority
    timestamp: int  # 2 bytes (uint16 delta from reference)
    device_id: int  # 1 byte
    lat_delta: int  # 2 bytes (int16, scaled to 0.001°)
    lon_delta: int  # 2 bytes (int16, scaled to 0.001°)
    depth_m: int    # 1 byte (uint8, 0-255m)
    battery_pct: int  # 1 byte (0-100)
    temperature_c: int  # 1 byte (int8, -50 to +50°C)
    status_flags: int  # 1 byte (error flags)

    def to_bytes(self) -> bytes:
        """Pack into fixed 12-byte payload."""
        return struct.pack(
            '<BHBhhBBbB',
            self.priority,
            self.timestamp,
            self.device_id,
            self.lat_delta,
            self.lon_delta,
            self.depth_m,
            self.battery_pct,
            self.temperature_c,
            self.status_flags
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'CompressedTelemetry':
        """Unpack from bytes."""
        (priority, timestamp, device_id, lat_delta, lon_delta,
         depth_m, battery_pct, temp_c, flags) = struct.unpack(
            '<BHBhhBBbB', data)
        return cls(
            priority=priority,
            timestamp=timestamp,
            device_id=device_id,
            lat_delta=lat_delta,
            lon_delta=lon_delta,
            depth_m=depth_m,
            battery_pct=battery_pct,
            temperature_c=temp_c,
            status_flags=flags
        )

    def size(self) -> int:
        """Return payload size in bytes."""
        return 12


class BandwidthPriorityQueue:
    """
    Adaptive queue that drops data based on available bandwidth.
    Critical data ALWAYS sent, low-priority dropped first.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.queue: Dict[DataPriority, List[CompressedTelemetry]] = {
            priority: [] for priority in DataPriority
        }
        self.reference_lat = 34.9821
        self.reference_lon = 33.9512
        self.reference_timestamp = int(time.time())
        self.bytes_sent = 0
        self.packets_dropped = 0

    def enqueue(self, record: Dict, priority: DataPriority):
        """Add record to priority queue."""
        try:
            # Convert full record to compressed format
            lat_delta = int((record.get('lat', self.reference_lat) - self.reference_lat) * 1000)
            lon_delta = int((record.get('lon', self.reference_lon) - self.reference_lon) * 1000)

            # Clamp to int16 range (-32768 to 32767)
            lat_delta = max(-32768, min(32767, lat_delta))
            lon_delta = max(-32768, min(32767, lon_delta))

            # Timestamp delta (2 bytes: 0-65535 seconds, ~18 hours)
            ts = int(record.get('timestamp', time.time()))
            ts_delta = (ts - self.reference_timestamp) & 0xFFFF

            # Normalize other values
            depth = int(min(255, max(0, record.get('depth_m', 0))))
            battery = int(min(100, max(0, record.get('battery_pct', 50))))
            temp = int(min(127, max(-128, record.get('temperature_c', 20))))

            # Status flags (error conditions)
            status = 0
            if record.get('battery_pct', 100) < 20:
                status |= 0x01  # Low battery
            if record.get('error'):
                status |= 0x02  # Error flag

            compressed = CompressedTelemetry(
                priority=priority,
                timestamp=ts_delta,
                device_id=record.get('device_id', 1),
                lat_delta=lat_delta,
                lon_delta=lon_delta,
                depth_m=depth,
                battery_pct=battery,
                temperature_c=temp,
                status_flags=status
            )

            self.queue[priority].append(compressed)

        except Exception as e:
            self.logger.error(f"Queue enqueue error: {e}")

    def get_packets_for_bandwidth(self, bandwidth_kbps: float) -> List[bytes]:
        """
        Select packets based on available bandwidth.
        Returns list of (priority, bytes) tuples.
        """
        mode = self._calculate_mode(bandwidth_kbps)
        self.logger.info(f"Bandwidth mode: {mode.name} ({bandwidth_kbps} kbps)")

        packets = []
        byte_limit = self._get_byte_limit(mode, bandwidth_kbps)
        bytes_used = 0

        # Priority-ordered extraction
        priority_order = [DataPriority.CRITICAL, DataPriority.SAFETY,
                         DataPriority.SCIENCE, DataPriority.TELEMETRY, DataPriority.DEBUG]

        for priority in priority_order:
            while self.queue[priority] and bytes_used < byte_limit:
                packet = self.queue[priority].pop(0)
                payload = packet.to_bytes()

                packets.append(payload)
                bytes_used += packet.size()
                self.bytes_sent += packet.size()

                # Stop adding low-priority if space running out
                if priority > DataPriority.SAFETY and bytes_used > byte_limit * 0.8:
                    break

        # Count dropped packets
        for priority in DataPriority:
            dropped = len(self.queue[priority])
            if dropped > 0 and priority > DataPriority.SAFETY:
                self.packets_dropped += dropped
                self.logger.warning(f"Dropped {dropped} packets (priority {priority.name})")

        return packets

    def _calculate_mode(self, bandwidth_kbps: float) -> BandwidthMode:
        """Determine current bandwidth mode."""
        if bandwidth_kbps > 100:
            return BandwidthMode.LUXE
        elif bandwidth_kbps > 10:
            return BandwidthMode.NORMAL
        elif bandwidth_kbps > 1:
            return BandwidthMode.CONSTRAINED
        else:
            return BandwidthMode.CRITICAL

    def _get_byte_limit(self, mode: BandwidthMode, bandwidth_kbps: float) -> int:
        """
        Calculate safe byte transmission limit.
        Uses 80% of available bandwidth, 20% reserved for protocol overhead.
        """
        seconds_per_transmission = 1.0  # Send once per second
        usable_bits = bandwidth_kbps * 1000 * 0.8 * seconds_per_transmission
        usable_bytes = int(usable_bits / 8)

        # Per mode minimums
        minimums = {
            BandwidthMode.LUXE: 256,
            BandwidthMode.NORMAL: 64,
            BandwidthMode.CONSTRAINED: 16,
            BandwidthMode.CRITICAL: 12  # Minimum: one GPS record
        }

        return max(minimums[mode], usable_bytes)

    def get_stats(self) -> Dict:
        """Queue statistics."""
        queue_depth = sum(len(v) for v in self.queue.values())
        return {
            "queue_depth": queue_depth,
            "bytes_sent_total": self.bytes_sent,
            "packets_dropped_total": self.packets_dropped,
            "queue_by_priority": {p.name: len(v) for p, v in self.queue.items()}
        }


class BandwidthAdaptiveEncoder:
    """
    High-level encoder that adapts to network conditions.
    Monitors actual throughput, detects congestion.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.queue = BandwidthPriorityQueue(logger)
        self.estimated_bandwidth = 10.0  # kbps, initial estimate
        self.last_transmission_time = time.time()
        self.transmission_history = []  # Track last 10 transmissions

    def submit_data(self, record: Dict, priority: DataPriority = DataPriority.SCIENCE):
        """Submit data to encoder."""
        self.queue.enqueue(record, priority)

    def submit_critical(self, gps: tuple, battery: int, timestamp: float):
        """Submit critical data (GPS + battery)."""
        record = {
            "lat": gps[0],
            "lon": gps[1],
            "battery_pct": battery,
            "timestamp": timestamp,
            "device_id": 1
        }
        self.queue.enqueue(record, DataPriority.CRITICAL)

    def transmit(self) -> Optional[bytes]:
        """
        Get packets ready for transmission.
        Returns concatenated bytes ready to send over LoRa/satellite.
        """
        # Get packets for current bandwidth estimate
        packets = self.queue.get_packets_for_bandwidth(self.estimated_bandwidth)

        if packets:
            # Concatenate all packets
            payload = b''.join(packets)

            # Record transmission
            now = time.time()
            elapsed = now - self.last_transmission_time
            self.transmission_history.append({
                "time": now,
                "bytes": len(payload),
                "interval": elapsed
            })

            # Keep only last 10 transmissions
            if len(self.transmission_history) > 10:
                self.transmission_history.pop(0)

            # Update bandwidth estimate (moving average)
            self._update_bandwidth_estimate()

            self.last_transmission_time = now
            return payload

        return None

    def _update_bandwidth_estimate(self):
        """
        Estimate actual bandwidth from transmission history.
        If transmissions are getting delayed, reduce estimate.
        """
        if len(self.transmission_history) < 2:
            return

        # Check if transmissions are spacing out (congestion sign)
        last_intervals = [t["interval"] for t in self.transmission_history[-5:]]
        avg_interval = sum(last_intervals) / len(last_intervals)

        if avg_interval > 2.0:  # Taking > 2 sec per transmission
            # Reduce bandwidth estimate
            self.estimated_bandwidth *= 0.9
            self.logger.warning(
                f"Congestion detected: reducing bandwidth estimate to {self.estimated_bandwidth:.1f} kbps"
            )

        elif avg_interval < 0.5:  # Transmitting < 500ms apart
            # Increase bandwidth estimate
            self.estimated_bandwidth *= 1.05
            self.logger.info(f"Good throughput: bandwidth estimate {self.estimated_bandwidth:.1f} kbps")

    def get_status(self) -> Dict:
        """Return encoder status."""
        return {
            "estimated_bandwidth_kbps": self.estimated_bandwidth,
            "queue": self.queue.get_stats(),
            "avg_transmission_interval": (
                sum(t["interval"] for t in self.transmission_history) / len(self.transmission_history)
                if self.transmission_history else 0
            )
        }


# ============ Example Usage ============

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    logger = logging.getLogger("bandwidth_encoder")

    encoder = BandwidthAdaptiveEncoder(logger)

    # Simulate 60 seconds of operation with varying bandwidth
    for sec in range(60):
        # Add data samples
        encoder.submit_critical(
            gps=(34.9821 + sec * 0.001, 33.9512 + sec * 0.001),
            battery=100 - (sec // 10),
            timestamp=time.time()
        )

        # Add science data
        encoder.submit_data({
            "lat": 34.9821,
            "lon": 33.9512,
            "depth_m": 15.5,
            "temperature_c": 12.0 - (sec / 100),
            "timestamp": time.time()
        }, DataPriority.SCIENCE)

        # Simulate bandwidth degradation (1 kbps after 30 sec)
        if sec > 30:
            encoder.estimated_bandwidth = 1.0

        # Transmit
        payload = encoder.transmit()
        if payload:
            logger.info(f"[{sec}s] Transmitted {len(payload)} bytes")

        time.sleep(1)

    # Final stats
    status = encoder.get_status()
    print("\n=== Final Status ===")
    print(f"Queue: {status['queue']}")
    print(f"Bandwidth: {status['estimated_bandwidth_kbps']:.1f} kbps")
