package org.o2monitor.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Same fields and defaults as contract/monitor_config.default.json and vision/o2gauge/config.py.
 * LOW / CRITICAL are PLACEHOLDERS until the hospital confirms them; the live values come
 * from Firestore devices/{id}.config and are cached on the tablet.
 */
@Serializable
data class MonitorConfig(
    @SerialName("low_threshold") val lowThreshold: Double = 3.5,
    @SerialName("critical_threshold") val criticalThreshold: Double = 3.0,
    val hysteresis: Double = 0.2,
    @SerialName("confirm_count") val confirmCount: Int = 3,
    @SerialName("median_window") val medianWindow: Int = 5,
    @SerialName("trend_rate_per_min") val trendRatePerMin: Double = 0.5,
    @SerialName("trend_window_s") val trendWindowS: Double = 60.0,
    @SerialName("trend_min_points") val trendMinPoints: Int = 8,
    @SerialName("min_confidence") val minConfidence: Double = 0.5,
    @SerialName("agree_tolerance") val agreeTolerance: Double = 0.4,
    @SerialName("lamp_low_setpoint") val lampLowSetpoint: Double? = null,
    @SerialName("lamp_tolerance") val lampTolerance: Double = 0.5,
    @SerialName("lost_after_s") val lostAfterS: Double = 30.0,
    @SerialName("battery_low_pct") val batteryLowPct: Int = 15,
    @SerialName("heartbeat_s") val heartbeatS: Int = 30,
) {
    fun validate(): MonitorConfig {
        require(criticalThreshold < lowThreshold) { "critical_threshold must be below low_threshold" }
        require(hysteresis >= 0 && confirmCount >= 1 && medianWindow >= 1) { "bad hysteresis/confirm/window" }
        require(minConfidence in 0.0..1.0) { "min_confidence must be in [0,1]" }
        return this
    }

    fun toJson(): String = JSON.encodeToString(serializer(), this)

    companion object {
        val JSON = Json { ignoreUnknownKeys = true; encodeDefaults = true; explicitNulls = true }
        fun fromJson(s: String): MonitorConfig = JSON.decodeFromString(serializer(), s).validate()
    }
}
