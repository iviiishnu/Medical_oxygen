package org.o2monitor.core

/**
 * Line-by-line port of vision/o2gauge/alert_engine.py. Both must pass
 * contract/alert_scenarios.json (see AlertEngineScenarioTest).
 *
 *  smoothing    median of the last medianWindow VALID readings
 *  confirmation confirmCount consecutive valid readings below threshold AND median below it
 *  hysteresis   clear after confirmCount medians >= threshold + hysteresis
 *  trend        least-squares fall rate over trendWindowS >= trendRatePerMin
 *  panel lamp   confirmed LOW lamp raises LOW even if the needle disagrees
 *  uncertain    confirmCount consecutive unusable frames
 *  fail-safe    no valid reading / lamp OFF for lostAfterS, or battery low -> MONITORING_LOST
 *  alarms never clear on bad data
 * Not thread-safe: call from one thread (the monitor loop).
 */
class AlertEngine(val cfg: MonitorConfig) {

    data class Input(
        val ts: Double,                  // seconds
        val value: Double?,
        val confidence: Double,
        val methodAgree: Boolean,
        val lampState: String = LampState.UNKNOWN,
        val batteryPct: Double? = null,
        val charging: Boolean = true,
    )

    sealed class Event {
        data class StatusChange(val from: String, val to: String, val ts: Double) : Event()
        data class Trend(val active: Boolean, val ts: Double) : Event()
    }

    data class Output(
        val status: String,
        val alarm: String,
        val value: Double?,
        val trendFalling: Boolean,
        val fallRatePerMin: Double?,
        val lostReason: String?,
        val events: List<Event>,
    )

    private val window = ArrayDeque<Double>()
    private val trendBuf = ArrayDeque<Pair<Double, Double>>()
    var alarm = Status.OK; private set
    private var lowStreak = 0
    private var critStreak = 0
    private var clearStreak = 0
    private var lampLowStreak = 0
    private var uncertainStreak = 0
    private var lastValidTs: Double? = null
    private var startTs: Double? = null
    private var lampOffSince: Double? = null
    private var batteryLow = false
    private var trendFalling = false
    private var fallRate: Double? = null
    private var lastStatus = Status.OK
    private var lastTrend = false

    init { cfg.validate() }

    fun update(r: Input): Output {
        val c = cfg
        if (startTs == null) startTs = r.ts
        val v = r.value
        val valid = v != null && r.confidence >= c.minConfidence && r.methodAgree

        lampLowStreak = if (r.lampState == LampState.LOW) lampLowStreak + 1 else 0
        if (r.lampState == LampState.OFF) {
            if (lampOffSince == null) lampOffSince = r.ts
        } else {
            lampOffSince = null
        }
        batteryLow = r.batteryPct != null && r.batteryPct < c.batteryLowPct && !r.charging

        if (valid) {
            val lv = lastValidTs
            if (lv != null && r.ts - lv >= c.lostAfterS) {
                window.clear(); trendBuf.clear()
                lowStreak = 0; critStreak = 0; clearStreak = 0
                trendFalling = false; fallRate = null
            }
            uncertainStreak = 0
            lastValidTs = r.ts
            window.addLast(v!!)
            while (window.size > c.medianWindow) window.removeFirst()
            trendBuf.addLast(Pair(r.ts, v))
            while (trendBuf.isNotEmpty() && r.ts - trendBuf.first().first > c.trendWindowS) trendBuf.removeFirst()
            updatePressureAlarm(v)
            updateTrend()
        } else {
            uncertainStreak += 1
        }

        if (lampLowStreak >= c.confirmCount && alarm == Status.OK) {
            alarm = Status.LOW
            clearStreak = 0
        }
        return emit(r.ts)
    }

    /** Watchdog: call every second even when no frame arrives. */
    fun tick(ts: Double): Output {
        if (startTs == null) startTs = ts
        return emit(ts)
    }

    fun median(): Double? {
        if (window.isEmpty()) return null
        val s = window.sorted()
        val n = s.size
        return if (n % 2 == 1) s[n / 2] else (s[n / 2 - 1] + s[n / 2]) / 2.0
    }

    private fun updatePressureAlarm(v: Double) {
        val c = cfg
        val med = median()!!
        critStreak = if (v < c.criticalThreshold) critStreak + 1 else 0
        lowStreak = if (v < c.lowThreshold) lowStreak + 1 else 0

        if (critStreak >= c.confirmCount && med < c.criticalThreshold) {
            if (alarm != Status.CRITICAL) clearStreak = 0
            alarm = Status.CRITICAL
        } else if (lowStreak >= c.confirmCount && med < c.lowThreshold && alarm == Status.OK) {
            alarm = Status.LOW
            clearStreak = 0
        }

        if (alarm == Status.CRITICAL) {
            if (med >= c.criticalThreshold + c.hysteresis) {
                clearStreak += 1
                if (clearStreak >= c.confirmCount) { alarm = Status.LOW; clearStreak = 0 }
            } else {
                clearStreak = 0
            }
        } else if (alarm == Status.LOW) {
            val lampLow = lampLowStreak > 0
            if (med >= c.lowThreshold + c.hysteresis && !lampLow) {
                clearStreak += 1
                if (clearStreak >= c.confirmCount) { alarm = Status.OK; clearStreak = 0 }
            } else {
                clearStreak = 0
            }
        }
    }

    private fun updateTrend() {
        val c = cfg
        val pts = trendBuf
        if (pts.size < c.trendMinPoints || pts.last().first - pts.first().first < c.trendWindowS * 0.5) {
            fallRate = null
            return
        }
        val n = pts.size
        val mt = pts.sumOf { it.first } / n
        val mv = pts.sumOf { it.second } / n
        val sxx = pts.sumOf { (it.first - mt) * (it.first - mt) }
        if (sxx <= 0) return
        val slope = pts.sumOf { (it.first - mt) * (it.second - mv) } / sxx
        val rate = -slope * 60.0
        fallRate = Math.round(rate * 10000.0) / 10000.0
        if (rate >= c.trendRatePerMin) trendFalling = true
        else if (rate < c.trendRatePerMin * 0.5) trendFalling = false
    }

    private fun lostReason(ts: Double): String? {
        val ref = lastValidTs ?: startTs!!
        if (ts - ref >= cfg.lostAfterS) return "no_valid_reading"
        val off = lampOffSince
        if (off != null && ts - off >= cfg.lostAfterS) return "lamp_off"
        if (batteryLow) return "battery_low"
        return null
    }

    private fun emit(ts: Double): Output {
        val lost = lostReason(ts)
        val status = when {
            lost != null -> Status.MONITORING_LOST
            alarm != Status.OK -> alarm
            uncertainStreak >= cfg.confirmCount -> Status.UNCERTAIN
            else -> Status.OK
        }
        val events = mutableListOf<Event>()
        if (status != lastStatus) {
            events += Event.StatusChange(lastStatus, status, ts)
            lastStatus = status
        }
        if (trendFalling != lastTrend) {
            events += Event.Trend(trendFalling, ts)
            lastTrend = trendFalling
        }
        val med = median()?.let { Math.round(it * 1000.0) / 1000.0 }
        return Output(status, alarm, med, trendFalling, fallRate, lost, events)
    }
}
