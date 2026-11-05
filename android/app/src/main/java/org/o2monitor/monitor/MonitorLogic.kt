package org.o2monitor.monitor

import org.o2monitor.core.AlertEngine
import org.o2monitor.core.MonitorConfig
import org.o2monitor.core.Reading
import org.o2monitor.core.Status
import org.o2monitor.vision.FrameResult

/**
 * Pure (Android-free) orchestration on the tablet:
 *   frame result -> AlertEngine -> which alerts to open/resolve, when to persist,
 *   whether the local alarm should ring.
 * Three independent alert "tracks", so one never hides another:
 *   pressure   : engine.alarm   (LOW / CRITICAL)
 *   monitoring : status MONITORING_LOST / UNCERTAIN
 *   trend      : TREND_FALLING
 */
class MonitorLogic(
    cfg: MonitorConfig,
    private val liveUpdateS: Double = 10.0,
    private val historyEveryS: Double = 60.0,
    private val uncertainAlertAfterS: Double = 10.0,
) {
    private var uncertainSinceMs: Long? = null
    val engine = AlertEngine(cfg)

    sealed class Action {
        data class OpenAlert(val type: String, val value: Double?, val reason: String?, val reading: Reading?) : Action()
        data class ResolveAlert(val type: String, val value: Double?) : Action()
        data class SaveHistory(val reading: Reading, val engineStatus: String, val smoothed: Double?) : Action()
        data class PushLive(val state: State) : Action()
    }

    data class State(
        val status: String = Status.OK,
        val alarm: String = Status.OK,
        val value: Double? = null,
        val rawValue: Double? = null,
        val confidence: Double = 0.0,
        val lampState: String = "UNKNOWN",
        val frameStatus: String = Status.OK,
        val trendFalling: Boolean = false,
        val fallRatePerMin: Double? = null,
        val lostReason: String? = null,
        val lastFrameEpochMs: Long? = null,
        val lastValidEpochMs: Long? = null,
        val inferenceMs: Double = 0.0,
        val openAlerts: Set<String> = emptySet(),
        val localAlarm: Boolean = false,
        val silencedUntilMs: Long = 0,
    )

    var state = State(); private set
    private var lastLiveMs = Long.MIN_VALUE / 2
    private var lastHistoryMs = Long.MIN_VALUE / 2
    private var pressureAlert: String? = null
    private var monitoringAlert: String? = null
    private var trendAlert = false
    private var lastSeverity = 0

    fun onFrame(fr: FrameResult, nowMs: Long, batteryPct: Double?, charging: Boolean): List<Action> {
        val r = fr.reading
        val out = engine.update(
            AlertEngine.Input(nowMs / 1000.0, r.value, r.confidence, r.methodAgree, r.lampState, batteryPct, charging),
        )
        val valid = r.value != null && r.confidence >= engine.cfg.minConfidence && r.methodAgree
        state = state.copy(
            rawValue = r.value, confidence = r.confidence, lampState = r.lampState, frameStatus = r.status,
            lastFrameEpochMs = nowMs, lastValidEpochMs = if (valid) nowMs else state.lastValidEpochMs,
            inferenceMs = fr.inferenceMs,
        )
        return apply(out, nowMs, r)
    }

    /** Watchdog tick (every second, even if the camera delivers nothing). */
    fun onTick(nowMs: Long): List<Action> = apply(engine.tick(nowMs / 1000.0), nowMs, null)

    /** Staff pressed "silence" on the tablet: quiet for [minutes]; re-rings on anything worse. */
    fun silence(nowMs: Long, minutes: Int = 5) {
        state = state.copy(silencedUntilMs = nowMs + minutes * 60_000L, localAlarm = false)
    }

    private fun severityOf(alerts: Set<String>): Int = alerts.maxOfOrNull { SEVERITY[it] ?: 1 } ?: 0

    private fun apply(o: AlertEngine.Output, nowMs: Long, reading: Reading?): List<Action> {
        val actions = mutableListOf<Action>()
        // pressure track
        val wantPressure = o.alarm.takeIf { it != Status.OK }
        if (wantPressure != pressureAlert) {
            pressureAlert?.let { actions += Action.ResolveAlert(it, o.value) }
            wantPressure?.let { actions += Action.OpenAlert(it, o.value, null, reading) }
            pressureAlert = wantPressure
        }
        // monitoring track. Brief UNCERTAIN spells (a few glare frames) only show on the tablet;
        // they become an alert after uncertainAlertAfterS. MONITORING_LOST alerts immediately.
        if (o.status == Status.UNCERTAIN) {
            if (uncertainSinceMs == null) uncertainSinceMs = nowMs
        } else {
            uncertainSinceMs = null
        }
        val uncertainLongEnough = uncertainSinceMs?.let { nowMs - it >= uncertainAlertAfterS * 1000 } ?: false
        val wantMon = when {
            o.status == Status.MONITORING_LOST -> o.status
            o.status == Status.UNCERTAIN && (uncertainLongEnough || monitoringAlert == Status.UNCERTAIN) -> o.status
            else -> null
        }
        if (wantMon != monitoringAlert) {
            monitoringAlert?.let { actions += Action.ResolveAlert(it, o.value) }
            wantMon?.let { actions += Action.OpenAlert(it, o.value, o.lostReason, reading) }
            monitoringAlert = wantMon
        }
        // trend track
        if (o.trendFalling != trendAlert) {
            actions += if (o.trendFalling) Action.OpenAlert(TREND, o.value, "fall ${o.fallRatePerMin}/min", reading)
            else Action.ResolveAlert(TREND, o.value)
            trendAlert = o.trendFalling
        }

        val open = setOfNotNull(pressureAlert, monitoringAlert, if (trendAlert) TREND else null)
        val sev = severityOf(open)
        var silencedUntil = state.silencedUntilMs
        if (sev > lastSeverity) silencedUntil = 0         // anything worse cancels the silence
        lastSeverity = sev
        val ringing = open.isNotEmpty() && nowMs >= silencedUntil

        val statusChanged = o.status != state.status || o.alarm != state.alarm || o.trendFalling != state.trendFalling
        state = state.copy(
            status = o.status, alarm = o.alarm, value = o.value, trendFalling = o.trendFalling,
            fallRatePerMin = o.fallRatePerMin, lostReason = o.lostReason, openAlerts = open,
            localAlarm = ringing, silencedUntilMs = silencedUntil,
        )
        if (reading != null && (nowMs - lastHistoryMs >= historyEveryS * 1000 || statusChanged)) {
            actions += Action.SaveHistory(reading, o.status, o.value)
            lastHistoryMs = nowMs
        }
        if (statusChanged || nowMs - lastLiveMs >= liveUpdateS * 1000) {
            actions += Action.PushLive(state)
            lastLiveMs = nowMs
        }
        return actions
    }

    companion object {
        const val TREND = "TREND_FALLING"
        val SEVERITY = mapOf(
            Status.CRITICAL to 5, Status.LOW to 4, Status.MONITORING_LOST to 4,
            Status.UNCERTAIN to 3, TREND to 2,
        )
    }
}
