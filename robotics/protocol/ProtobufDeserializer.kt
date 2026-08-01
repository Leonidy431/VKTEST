/**
 * Protocol Buffers Deserialization (Kotlin/Android)
 *
 * Receives hex-encoded binary telemetry from Firebase
 * Validates CRC32 and sequence numbers
 * Parses into typed data structures for UI/dashboard
 */

package com.leonidy431.vktest.robotics.protocol

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.CRC32
import kotlin.math.abs

data class GpsCoordinates(
    val latitude: Double,
    val longitude: Double,
    val accuracyMeters: Int = 0
)

data class SensorData(
    val depthM: Float,
    val temperatureC: Float,
    val salinityPpt: Float,
    val batteryPct: Int,
    val signalQualityPct: Int,
    val headingDegrees: Int,
    val velocityMs: Float
)

data class TelemetryMessage(
    val sequenceId: UInt,
    val timestampUnixMs: Long,
    val robotId: String,
    val messageType: String,
    val gps: GpsCoordinates,
    val sensors: SensorData,
    val currentState: String,
    val queueDepth: Int,
    val crc32: UInt
)

data class CommandAck(
    val commandId: Int,
    val receivedTimestampUnixMs: Long,
    val robotId: String,
    val accepted: Boolean,
    val rejectReason: String,
    val executionStatus: String,
    val executionProgressPct: Int,
    val crc32: UInt
)

data class HomingInitiated(
    val sequenceId: UInt,
    val timestampUnixMs: Long,
    val robotId: String,
    val reason: String,
    val estimatedReturnTimeSec: Int,
    val lastKnownPosition: GpsCoordinates,
    val batteryPct: Int,
    val strategy: String,
    val crc32: UInt
)

class ProtobufDeserializer {

    companion object {
        /**
         * Deserialize hex-encoded telemetry message
         */
        fun decodeTelemetry(hexString: String): TelemetryMessage {
            val data = hexStringToByteArray(hexString)
            return decodeTelemetryFromBytes(data)
        }

        /**
         * Deserialize binary telemetry message
         */
        fun decodeTelemetryFromBytes(data: ByteArray): TelemetryMessage {
            val buffer = ByteBuffer.wrap(data).apply {
                order(ByteOrder.LITTLE_ENDIAN)
            }

            try {
                // Header
                val sequenceId = buffer.int.toUInt()
                val timestampMs = buffer.long
                val robotIdLen = buffer.short.toInt()
                val robotIdBytes = ByteArray(robotIdLen)
                buffer.get(robotIdBytes)
                val robotId = String(robotIdBytes)

                // Message type
                val msgTypeLen = buffer.short.toInt()
                val msgTypeBytes = ByteArray(msgTypeLen)
                buffer.get(msgTypeBytes)
                val messageType = String(msgTypeBytes)

                // GPS
                val lat = buffer.double
                val lon = buffer.double
                val accuracy = buffer.int
                val gps = GpsCoordinates(lat, lon, accuracy)

                // Sensors
                val depth = buffer.float
                val temp = buffer.float
                val salinity = buffer.float
                val battery = buffer.int
                val signal = buffer.int
                val heading = buffer.short.toInt()
                val velocity = buffer.float
                val sensors = SensorData(depth, temp, salinity, battery, signal, heading, velocity)

                // State
                val stateLen = buffer.short.toInt()
                val stateBytes = ByteArray(stateLen)
                buffer.get(stateBytes)
                val currentState = String(stateBytes)

                // Queue depth
                val queueDepth = buffer.int

                // CRC32 (stored)
                val crc32Stored = buffer.int.toUInt()

                // Verify CRC32
                val messageData = data.sliceArray(0 until data.size - 4)
                val crc32Calc = calculateCrc32(messageData)

                if (crc32Calc != crc32Stored) {
                    throw IllegalArgumentException(
                        "CRC32 mismatch: expected ${crc32Stored.toString(16)}, got ${crc32Calc.toString(16)}"
                    )
                }

                return TelemetryMessage(
                    sequenceId, timestampMs, robotId, messageType,
                    gps, sensors, currentState, queueDepth, crc32Stored
                )

            } catch (e: Exception) {
                throw RuntimeException("Failed to deserialize telemetry: ${e.message}", e)
            }
        }

        /**
         * Deserialize hex-encoded ACK message
         */
        fun decodeAck(hexString: String): CommandAck {
            val data = hexStringToByteArray(hexString)
            val buffer = ByteBuffer.wrap(data).apply {
                order(ByteOrder.LITTLE_ENDIAN)
            }

            try {
                val commandId = buffer.int
                val timestampMs = buffer.long
                val robotIdLen = buffer.short.toInt()
                val robotIdBytes = ByteArray(robotIdLen)
                buffer.get(robotIdBytes)
                val robotId = String(robotIdBytes)

                val accepted = buffer.get() == 1.toByte()
                val rejectReasonLen = buffer.short.toInt()
                val rejectReasonBytes = ByteArray(rejectReasonLen)
                buffer.get(rejectReasonBytes)
                val rejectReason = String(rejectReasonBytes)

                val statusLen = buffer.short.toInt()
                val statusBytes = ByteArray(statusLen)
                buffer.get(statusBytes)
                val executionStatus = String(statusBytes)

                val progressPct = buffer.get().toInt()

                val crc32Stored = buffer.int.toUInt()

                // Verify CRC32
                val messageData = data.sliceArray(0 until data.size - 4)
                val crc32Calc = calculateCrc32(messageData)

                if (crc32Calc != crc32Stored) {
                    throw IllegalArgumentException("CRC32 mismatch in ACK")
                }

                return CommandAck(
                    commandId, timestampMs, robotId, accepted, rejectReason,
                    executionStatus, progressPct, crc32Stored
                )

            } catch (e: Exception) {
                throw RuntimeException("Failed to deserialize ACK: ${e.message}", e)
            }
        }

        /**
         * Deserialize hex-encoded homing message
         */
        fun decodeHoming(hexString: String): HomingInitiated {
            val data = hexStringToByteArray(hexString)
            val buffer = ByteBuffer.wrap(data).apply {
                order(ByteOrder.LITTLE_ENDIAN)
            }

            try {
                val sequenceId = buffer.int.toUInt()
                val timestampMs = buffer.long
                val robotIdLen = buffer.short.toInt()
                val robotIdBytes = ByteArray(robotIdLen)
                buffer.get(robotIdBytes)
                val robotId = String(robotIdBytes)

                val reasonLen = buffer.short.toInt()
                val reasonBytes = ByteArray(reasonLen)
                buffer.get(reasonBytes)
                val reason = String(reasonBytes)

                val returnTime = buffer.int
                val lat = buffer.double
                val lon = buffer.double
                val accuracy = buffer.int
                val position = GpsCoordinates(lat, lon, accuracy)

                val battery = buffer.get().toInt()

                val strategyLen = buffer.short.toInt()
                val strategyBytes = ByteArray(strategyLen)
                buffer.get(strategyBytes)
                val strategy = String(strategyBytes)

                val crc32Stored = buffer.int.toUInt()

                // Verify CRC32
                val messageData = data.sliceArray(0 until data.size - 4)
                val crc32Calc = calculateCrc32(messageData)

                if (crc32Calc != crc32Stored) {
                    throw IllegalArgumentException("CRC32 mismatch in Homing")
                }

                return HomingInitiated(
                    sequenceId, timestampMs, robotId, reason, returnTime,
                    position, battery, strategy, crc32Stored
                )

            } catch (e: Exception) {
                throw RuntimeException("Failed to deserialize homing: ${e.message}", e)
            }
        }

        /**
         * Validate sequence order and detect gaps
         */
        fun validateSequence(
            lastSequenceId: UInt,
            newSequenceId: UInt,
            onGapDetected: (expected: UInt, received: UInt) -> Unit = { _, _ -> }
        ): Boolean {
            if (lastSequenceId == 0U) return true  // First message

            val expectedNextId = (lastSequenceId + 1U)
            if (newSequenceId != expectedNextId) {
                val gap = if (newSequenceId > expectedNextId) {
                    newSequenceId - expectedNextId
                } else {
                    // Handle 32-bit wraparound
                    (UInt.MAX_VALUE - expectedNextId) + newSequenceId
                }
                onGapDetected(expectedNextId, newSequenceId)
                return false
            }
            return true
        }

        /**
         * Calculate latency from received timestamp
         */
        fun calculateLatency(messageTimestampMs: Long): Long {
            val now = System.currentTimeMillis()
            return now - messageTimestampMs
        }

        /**
         * Parse hexadecimal string to byte array
         */
        private fun hexStringToByteArray(s: String): ByteArray {
            val len = s.length
            val data = ByteArray(len / 2)
            for (i in 0 until len step 2) {
                data[i / 2] = ((s[i].toString().toInt(16) shl 4) +
                        s[i + 1].toString().toInt(16)).toByte()
            }
            return data
        }

        /**
         * Calculate CRC32 checksum
         */
        private fun calculateCrc32(data: ByteArray): UInt {
            val crc = CRC32()
            crc.update(data)
            return crc.value.toUInt()
        }

        /**
         * Format coordinates for display (2 decimal places)
         */
        fun formatCoordinates(gps: GpsCoordinates): String {
            return String.format("%.4f, %.4f", gps.latitude, gps.longitude)
        }

        /**
         * Format distance calculation using Haversine formula (km)
         */
        fun calculateDistance(gps1: GpsCoordinates, gps2: GpsCoordinates): Float {
            val R = 6371f  // Earth radius in km
            val dLat = Math.toRadians(gps2.latitude - gps1.latitude).toFloat()
            val dLon = Math.toRadians(gps2.longitude - gps1.longitude).toFloat()

            val a = kotlin.math.sin(dLat / 2) * kotlin.math.sin(dLat / 2) +
                    kotlin.math.cos(Math.toRadians(gps1.latitude).toFloat()) *
                    kotlin.math.cos(Math.toRadians(gps2.latitude).toFloat()) *
                    kotlin.math.sin(dLon / 2) * kotlin.math.sin(dLon / 2)

            val c = 2 * kotlin.math.atan2(kotlin.math.sqrt(a), kotlin.math.sqrt(1 - a))
            return R * c
        }
    }
}

/**
 * Dashboard data class for UI rendering
 */
data class RobotDashboardState(
    val robotId: String,
    val currentState: String,
    val lastSequenceId: UInt = 0U,
    val latestTelemetry: TelemetryMessage? = null,
    val lastAck: CommandAck? = null,
    val lastHoming: HomingInitiated? = null,
    val sequenceGaps: MutableList<Pair<UInt, UInt>> = mutableListOf(),
    val averageLatencyMs: Long = 0L,
    val batteryTrend: List<Int> = emptyList()
) {
    fun updateWithTelemetry(msg: TelemetryMessage) {
        // Update last sequence
        if (!ProtobufDeserializer.validateSequence(lastSequenceId, msg.sequenceId) { exp, rec ->
            sequenceGaps.add(Pair(exp, rec))
        }) {
            // Log gap but continue processing
        }
    }
}
