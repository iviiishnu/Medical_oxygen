package org.o2monitor.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** contract/reading.schema.json - one message per camera frame. */
@Serializable
data class Reading(
    @SerialName("device_id") val deviceId: String,
    @SerialName("gauge_id") val gaugeId: String,
    val ts: String,
    val value: Double?,
    val unit: String = "kg/cm2",
    val confidence: Double,
    @SerialName("lamp_state") val lampState: String,
    @SerialName("method_agree") val methodAgree: Boolean,
    val status: String,
)

object Status {
    const val OK = "OK"
    const val LOW = "LOW"
    const val CRITICAL = "CRITICAL"
    const val UNCERTAIN = "UNCERTAIN"
    const val MONITORING_LOST = "MONITORING_LOST"
    val ALL = listOf(OK, LOW, CRITICAL, UNCERTAIN, MONITORING_LOST)
}

object LampState {
    const val NORMAL = "NORMAL"
    const val LOW = "LOW"
    const val HIGH = "HIGH"
    const val OFF = "OFF"
    const val CONFLICT = "CONFLICT"
    const val UNKNOWN = "UNKNOWN"
    val LIT = setOf(NORMAL, LOW, HIGH)
}
