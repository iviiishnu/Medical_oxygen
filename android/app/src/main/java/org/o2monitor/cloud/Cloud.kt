package org.o2monitor.cloud

import org.o2monitor.core.MonitorConfig
import org.o2monitor.core.Reading
import org.o2monitor.monitor.MonitorLogic
import org.o2monitor.vision.Calibration
import java.io.Closeable

data class DeviceView(
    val id: String,
    val name: String,
    val value: Double?,
    val unit: String,
    val status: String,
    val alarm: String,
    val trendFalling: Boolean,
    val lastHeartbeatMs: Long?,
    val online: Boolean,
    val battery: Double?,
)

data class AlertView(
    val id: String,
    val type: String,
    val state: String,
    val deviceId: String,
    val value: Double?,
    val unit: String,
    val createdMs: Long?,
    val ackedByName: String?,
    val ackedMs: Long?,
    val resolvedMs: Long?,
)

/**
 * Everything the app sends to / reads from the backend. The tablet never WAITS on it:
 * all monitor-side calls are fire-and-forget (Firestore queues them offline).
 */
interface Cloud {
    val available: Boolean
    fun currentUid(): String?
    fun currentEmail(): String?
    fun signIn(email: String, password: String, done: (Result<String>) -> Unit)
    fun signOut()

    // ---- Monitor mode (tablet)
    fun pushLive(deviceId: String, s: MonitorLogic.State, r: Reading?, battery: Double?, charging: Boolean, appVersion: String)
    fun saveHistory(deviceId: String, r: Reading, engineStatus: String, smoothed: Double?)
    /** Returns the new alert id (generated locally, works offline). */
    fun openAlert(deviceId: String, gaugeId: String, type: String, value: Double?, unit: String,
                  reason: String?, snapshot: String?): String?
    fun resolveAlert(alertId: String, value: Double?)
    fun saveCalibration(deviceId: String, cal: Calibration)
    fun observeConfig(deviceId: String, onChange: (MonitorConfig) -> Unit): Closeable

    // ---- Staff mode (phones)
    fun observeDevices(cb: (List<DeviceView>) -> Unit): Closeable
    fun observeAlerts(cb: (List<AlertView>) -> Unit): Closeable
    fun acknowledge(alertId: String, name: String, done: (Result<Unit>) -> Unit)
    fun registerToken(token: String)
    fun setOnDuty(onDuty: Boolean)
}

/** Local-only build (no google-services.json): the tablet still reads and alarms locally. */
object NoopCloud : Cloud {
    private val none = Closeable { }
    override val available = false
    override fun currentUid(): String? = null
    override fun currentEmail(): String? = null
    override fun signIn(email: String, password: String, done: (Result<String>) -> Unit) =
        done(Result.failure(IllegalStateException("Firebase not configured in this build")))
    override fun signOut() {}
    override fun pushLive(deviceId: String, s: MonitorLogic.State, r: Reading?, battery: Double?, charging: Boolean, appVersion: String) {}
    override fun saveHistory(deviceId: String, r: Reading, engineStatus: String, smoothed: Double?) {}
    override fun openAlert(deviceId: String, gaugeId: String, type: String, value: Double?, unit: String,
                           reason: String?, snapshot: String?): String? = null
    override fun resolveAlert(alertId: String, value: Double?) {}
    override fun saveCalibration(deviceId: String, cal: Calibration) {}
    override fun observeConfig(deviceId: String, onChange: (MonitorConfig) -> Unit) = none
    override fun observeDevices(cb: (List<DeviceView>) -> Unit) = none
    override fun observeAlerts(cb: (List<AlertView>) -> Unit) = none
    override fun acknowledge(alertId: String, name: String, done: (Result<Unit>) -> Unit) =
        done(Result.failure(IllegalStateException("Firebase not configured in this build")))
    override fun registerToken(token: String) {}
    override fun setOnDuty(onDuty: Boolean) {}
}
