"""
Unit tests for Bandwidth-Optimized Data Prioritization Encoder

Tests cover:
- Data priority tiers and queue management
- Compression and serialization (fixed 12-byte format)
- Adaptive bandwidth mode selection
- Congestion detection and throttling
- Graceful degradation under bandwidth constraints
"""

import time
import struct
import pytest
import logging
import sys

sys.path.insert(0, '/home/user/VKTEST')

from robotics.telemetry_system.bandwidth_priority_encoder import (
    DataPriority,
    BandwidthMode,
    CompressedTelemetry,
    BandwidthPriorityQueue,
    BandwidthAdaptiveEncoder,
)


class TestDataPriority:
    """Test priority level definitions."""

    def test_priority_ordering(self):
        """Critical should be highest priority (lowest value)."""
        assert DataPriority.CRITICAL == 1
        assert DataPriority.SAFETY == 2
        assert DataPriority.SCIENCE == 3
        assert DataPriority.TELEMETRY == 4
        assert DataPriority.DEBUG == 5

    def test_priority_comparison(self):
        """Lower number = higher priority."""
        assert DataPriority.CRITICAL < DataPriority.DEBUG
        assert DataPriority.SAFETY < DataPriority.SCIENCE


class TestCompressedTelemetry:
    """Test compression and serialization."""

    def test_telemetry_creation(self):
        """Should create valid telemetry record."""
        record = CompressedTelemetry(
            priority=DataPriority.CRITICAL,
            timestamp=100,
            device_id=1,
            lat_delta=500,
            lon_delta=-300,
            depth_m=15,
            battery_pct=85,
            temperature_c=12,
            status_flags=0
        )
        assert record.priority == DataPriority.CRITICAL
        assert record.depth_m == 15

    def test_to_bytes_size(self):
        """Compressed telemetry should be exactly 12 bytes."""
        record = CompressedTelemetry(
            priority=DataPriority.CRITICAL,
            timestamp=100,
            device_id=1,
            lat_delta=0,
            lon_delta=0,
            depth_m=0,
            battery_pct=50,
            temperature_c=20,
            status_flags=0
        )
        payload = record.to_bytes()
        assert len(payload) == 12
        assert record.size() == 12

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        original = CompressedTelemetry(
            priority=DataPriority.SAFETY,
            timestamp=12345,
            device_id=2,
            lat_delta=1000,
            lon_delta=-500,
            depth_m=50,
            battery_pct=75,
            temperature_c=-5,
            status_flags=0x03
        )
        payload = original.to_bytes()
        restored = CompressedTelemetry.from_bytes(payload)

        assert restored.priority == original.priority
        assert restored.timestamp == original.timestamp
        assert restored.device_id == original.device_id
        assert restored.lat_delta == original.lat_delta
        assert restored.lon_delta == original.lon_delta
        assert restored.depth_m == original.depth_m
        assert restored.battery_pct == original.battery_pct
        assert restored.temperature_c == original.temperature_c
        assert restored.status_flags == original.status_flags

    def test_clamping_values(self):
        """Should handle clamped values correctly."""
        # Note: Values must be within valid ranges when creating CompressedTelemetry
        # The enqueue() method handles clamping before creating records
        record = CompressedTelemetry(
            priority=DataPriority.CRITICAL,
            timestamp=100,
            device_id=1,
            lat_delta=32767,  # Max int16
            lon_delta=-32768,  # Min int16
            depth_m=255,  # Max uint8
            battery_pct=100,  # Max battery
            temperature_c=127,  # Max int8
            status_flags=0xFF
        )
        # Values should serialize correctly
        payload = record.to_bytes()
        assert len(payload) == 12
        restored = CompressedTelemetry.from_bytes(payload)
        # Restored values should match originals
        assert restored.lat_delta == 32767
        assert restored.lon_delta == -32768
        assert restored.depth_m == 255
        assert restored.temperature_c == 127


class TestBandwidthMode:
    """Test bandwidth mode selection."""

    def test_bandwidth_modes(self):
        """Should have 4 distinct bandwidth modes."""
        assert BandwidthMode.LUXE == 0
        assert BandwidthMode.NORMAL == 1
        assert BandwidthMode.CONSTRAINED == 2
        assert BandwidthMode.CRITICAL == 3


class TestBandwidthPriorityQueue:
    """Test priority queue and bandwidth adaptation."""

    @pytest.fixture
    def queue(self):
        """Create test queue instance."""
        logger = logging.getLogger(__name__)
        return BandwidthPriorityQueue(logger)

    def test_queue_initialization(self, queue):
        """Queue should start empty."""
        stats = queue.get_stats()
        assert stats["queue_depth"] == 0
        assert stats["bytes_sent_total"] == 0
        assert stats["packets_dropped_total"] == 0

    def test_enqueue_critical_data(self, queue):
        """Should enqueue critical data (GPS + battery)."""
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 85,
            "timestamp": time.time(),
            "device_id": 1
        }
        queue.enqueue(record, DataPriority.CRITICAL)

        stats = queue.get_stats()
        assert stats["queue_depth"] == 1
        assert stats["queue_by_priority"]["CRITICAL"] == 1

    def test_enqueue_multiple_priorities(self, queue):
        """Should maintain separate queues per priority."""
        base_record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "timestamp": time.time(),
            "device_id": 1
        }

        queue.enqueue(base_record, DataPriority.CRITICAL)
        queue.enqueue(base_record, DataPriority.SAFETY)
        queue.enqueue(base_record, DataPriority.SCIENCE)

        stats = queue.get_stats()
        assert stats["queue_depth"] == 3
        assert stats["queue_by_priority"]["CRITICAL"] == 1
        assert stats["queue_by_priority"]["SAFETY"] == 1
        assert stats["queue_by_priority"]["SCIENCE"] == 1

    def test_enqueue_handles_missing_fields(self, queue):
        """Should handle incomplete records with defaults."""
        record = {"device_id": 1}  # Missing most fields
        queue.enqueue(record, DataPriority.SCIENCE)

        stats = queue.get_stats()
        assert stats["queue_depth"] == 1

    def test_calculate_mode_luxe(self, queue):
        """>100 kbps should be LUXE mode."""
        mode = queue._calculate_mode(150.0)
        assert mode == BandwidthMode.LUXE

    def test_calculate_mode_normal(self, queue):
        """10-100 kbps should be NORMAL mode."""
        mode = queue._calculate_mode(50.0)
        assert mode == BandwidthMode.NORMAL

    def test_calculate_mode_constrained(self, queue):
        """1-10 kbps should be CONSTRAINED mode."""
        mode = queue._calculate_mode(5.0)
        assert mode == BandwidthMode.CONSTRAINED

    def test_calculate_mode_critical(self, queue):
        """<1 kbps should be CRITICAL mode."""
        mode = queue._calculate_mode(0.5)
        assert mode == BandwidthMode.CRITICAL

    def test_byte_limit_luxe(self, queue):
        """LUXE mode should allow 256+ bytes."""
        limit = queue._get_byte_limit(BandwidthMode.LUXE, 200.0)
        assert limit >= 256

    def test_byte_limit_critical(self, queue):
        """CRITICAL mode should allow minimum 12 bytes (1 packet)."""
        # With 0.5 kbps: 0.5 * 1000 * 0.8 * 1.0 / 8 = 50 bytes
        # But minimum for CRITICAL is 12, so it should be max(12, 50) = 50
        limit = queue._get_byte_limit(BandwidthMode.CRITICAL, 0.5)
        assert limit >= 12  # At least one packet

    def test_get_packets_respects_bandwidth(self, queue):
        """Should prioritize critical packets over low-priority."""
        # Add multiple priority levels
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 85,
            "timestamp": time.time(),
            "device_id": 1
        }

        # Add 5 critical packets (60 bytes total)
        for i in range(5):
            queue.enqueue(record, DataPriority.CRITICAL)

        # Add 10 science packets (120 bytes total)
        for i in range(10):
            queue.enqueue(record, DataPriority.SCIENCE)

        # Request with limited bandwidth: 0.5 kbps = ~50 bytes in 1 sec
        packets = queue.get_packets_for_bandwidth(0.5)

        # Should prioritize critical over science; all critical should fit
        critical_count = len(packets)
        assert critical_count >= 4  # At least most critical packets

    def test_packets_are_bytes(self, queue):
        """get_packets_for_bandwidth should return list of bytes."""
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 85,
            "timestamp": time.time(),
            "device_id": 1
        }
        queue.enqueue(record, DataPriority.CRITICAL)

        packets = queue.get_packets_for_bandwidth(100.0)
        assert len(packets) == 1
        assert isinstance(packets[0], bytes)
        assert len(packets[0]) == 12

    def test_status_flags_low_battery(self, queue):
        """Should set low battery flag when battery < 20%."""
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 15,
            "timestamp": time.time(),
            "device_id": 1
        }
        queue.enqueue(record, DataPriority.SAFETY)

        packets = queue.get_packets_for_bandwidth(100.0)
        packet = CompressedTelemetry.from_bytes(packets[0])

        # Low battery flag (0x01) should be set
        assert packet.status_flags & 0x01 == 0x01

    def test_status_flags_error(self, queue):
        """Should set error flag when error present."""
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "battery_pct": 85,
            "timestamp": time.time(),
            "device_id": 1,
            "error": True
        }
        queue.enqueue(record, DataPriority.SAFETY)

        packets = queue.get_packets_for_bandwidth(100.0)
        packet = CompressedTelemetry.from_bytes(packets[0])

        # Error flag (0x02) should be set
        assert packet.status_flags & 0x02 == 0x02


class TestBandwidthAdaptiveEncoder:
    """Test high-level encoder with congestion detection."""

    @pytest.fixture
    def encoder(self):
        """Create test encoder instance."""
        logger = logging.getLogger(__name__)
        return BandwidthAdaptiveEncoder(logger)

    def test_encoder_initialization(self, encoder):
        """Should start with default bandwidth estimate."""
        assert encoder.estimated_bandwidth == 10.0
        status = encoder.get_status()
        assert status["estimated_bandwidth_kbps"] == 10.0

    def test_submit_critical_data(self, encoder):
        """Should accept critical GPS + battery data."""
        encoder.submit_critical(
            gps=(34.9821, 33.9512),
            battery=85,
            timestamp=time.time()
        )
        status = encoder.get_status()
        assert status["queue"]["queue_depth"] == 1

    def test_submit_science_data(self, encoder):
        """Should accept science telemetry."""
        record = {
            "lat": 34.9821,
            "lon": 33.9512,
            "depth_m": 15.5,
            "temperature_c": 12.0,
            "timestamp": time.time()
        }
        encoder.submit_data(record, DataPriority.SCIENCE)
        status = encoder.get_status()
        assert status["queue"]["queue_depth"] == 1

    def test_transmit_returns_bytes(self, encoder):
        """transmit() should return byte payload."""
        encoder.submit_critical(
            gps=(34.9821, 33.9512),
            battery=85,
            timestamp=time.time()
        )
        payload = encoder.transmit()
        assert isinstance(payload, bytes)
        assert len(payload) == 12  # One compressed packet

    def test_transmit_empty_queue_returns_none(self, encoder):
        """transmit() on empty queue should return None."""
        payload = encoder.transmit()
        assert payload is None

    def test_congestion_detection_reduces_bandwidth(self, encoder):
        """Should reduce bandwidth estimate on congestion."""
        initial_bandwidth = encoder.estimated_bandwidth

        # Add multiple transmissions with large gaps
        for i in range(5):
            encoder.submit_critical(
                gps=(34.9821, 33.9512),
                battery=85,
                timestamp=time.time()
            )
            payload = encoder.transmit()
            if payload:
                time.sleep(2.5)  # Simulate slow transmission

        # After congestion, bandwidth should decrease
        assert encoder.estimated_bandwidth < initial_bandwidth

    def test_good_throughput_increases_bandwidth(self, encoder):
        """Should increase bandwidth estimate on good throughput."""
        initial_bandwidth = encoder.estimated_bandwidth

        # Add multiple transmissions with small gaps
        for i in range(5):
            encoder.submit_critical(
                gps=(34.9821, 33.9512),
                battery=85,
                timestamp=time.time()
            )
            payload = encoder.transmit()
            if payload:
                time.sleep(0.3)  # Quick transmission

        # After good throughput, bandwidth should increase
        assert encoder.estimated_bandwidth > initial_bandwidth

    def test_transmission_history_kept(self, encoder):
        """Should maintain transmission history (last 10)."""
        for i in range(15):
            encoder.submit_critical(
                gps=(34.9821, 33.9512),
                battery=85,
                timestamp=time.time()
            )
            payload = encoder.transmit()

        # Should only keep last 10
        assert len(encoder.transmission_history) <= 10

    def test_avg_transmission_interval_calculation(self, encoder):
        """Should calculate average transmission interval."""
        for i in range(3):
            encoder.submit_critical(
                gps=(34.9821, 33.9512),
                battery=85,
                timestamp=time.time()
            )
            payload = encoder.transmit()
            time.sleep(0.1)

        status = encoder.get_status()
        assert status["avg_transmission_interval"] > 0

    def test_mixed_priority_transmission(self, encoder):
        """Should transmit mixed priorities in order."""
        encoder.submit_data(
            {
                "lat": 34.9821,
                "lon": 33.9512,
                "temperature_c": 12.0,
                "timestamp": time.time()
            },
            DataPriority.SCIENCE
        )
        encoder.submit_critical(
            gps=(34.9821, 33.9512),
            battery=85,
            timestamp=time.time()
        )

        payload = encoder.transmit()
        # Should contain 2 packets (24 bytes)
        assert len(payload) == 24

    def test_encoder_under_extreme_constraints(self, encoder):
        """Should handle extreme bandwidth constraint (0.5 kbps)."""
        encoder.estimated_bandwidth = 0.5

        # Add many low-priority packets
        for i in range(20):
            encoder.submit_data(
                {
                    "lat": 34.9821,
                    "lon": 33.9512,
                    "temperature_c": 12.0,
                    "timestamp": time.time()
                },
                DataPriority.DEBUG
            )

        # Critical data should still go through
        encoder.submit_critical(
            gps=(34.9821, 33.9512),
            battery=50,
            timestamp=time.time()
        )

        payload = encoder.transmit()
        # Should get at least the critical packet
        assert payload is not None
        assert len(payload) >= 12


class TestBandwidthIntegration:
    """Integration tests for bandwidth management."""

    def test_realistic_60_second_mission(self):
        """Simulate realistic 60-second AUV mission."""
        logger = logging.getLogger(__name__)
        encoder = BandwidthAdaptiveEncoder(logger)

        transmitted_bytes = 0
        for sec in range(60):
            # Add critical data every second
            encoder.submit_critical(
                gps=(34.9821 + sec * 0.001, 33.9512 + sec * 0.001),
                battery=100 - (sec // 10),
                timestamp=time.time()
            )

            # Add science data every 5 seconds
            if sec % 5 == 0:
                encoder.submit_data(
                    {
                        "lat": 34.9821,
                        "lon": 33.9512,
                        "depth_m": 15.5 + (sec / 100),
                        "temperature_c": 12.0 - (sec / 100),
                        "timestamp": time.time()
                    },
                    DataPriority.SCIENCE
                )

            # Simulate bandwidth degradation after 30 seconds
            if sec > 30:
                encoder.estimated_bandwidth = 1.0
            else:
                encoder.estimated_bandwidth = 10.0

            # Transmit
            payload = encoder.transmit()
            if payload:
                transmitted_bytes += len(payload)

        # Should have transmitted something
        assert transmitted_bytes > 0
        status = encoder.get_status()
        assert status["queue"]["bytes_sent_total"] == transmitted_bytes

    def test_critical_data_always_sent(self):
        """Critical data should be sent even under severe constraints."""
        logger = logging.getLogger(__name__)
        encoder = BandwidthAdaptiveEncoder(logger)
        encoder.estimated_bandwidth = 0.1  # Extremely constrained

        # Add critical data
        encoder.submit_critical(
            gps=(34.9821, 33.9512),
            battery=50,
            timestamp=time.time()
        )

        # Add lots of low-priority data
        for i in range(100):
            encoder.submit_data(
                {"lat": 34.9821, "lon": 33.9512, "timestamp": time.time()},
                DataPriority.DEBUG
            )

        payload = encoder.transmit()
        # Critical packet should still be sent
        assert payload is not None
        assert len(payload) >= 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
