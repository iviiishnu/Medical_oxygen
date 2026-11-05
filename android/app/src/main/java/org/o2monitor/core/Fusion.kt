package org.o2monitor.core

import kotlin.math.abs

/** Port of vision/o2gauge/fusion.py. */
data class NeedleResult(
    val value: Double?,
    val angle: Double?,
    val confidence: Double,
    val inRange: Boolean = true,
    val method: String = "stage_a",
    val reason: String = "",
)

data class Fused(
    val value: Double?,
    val confidence: Double,
    val methodAgree: Boolean,
    val lampAgree: Boolean,
    val status: String,
    val source: String,
    val notes: List<String>,
)

object Fusion {
    private fun setpoint(cfg: MonitorConfig) = cfg.lampLowSetpoint ?: cfg.lowThreshold

    fun lampExpected(value: Double, cfg: MonitorConfig) =
        if (value < setpoint(cfg)) LampState.LOW else LampState.NORMAL

    fun lampConsistent(value: Double?, lamp: String, cfg: MonitorConfig): Boolean {
        if (value == null || lamp !in LampState.LIT) return true
        if (abs(value - setpoint(cfg)) <= cfg.lampTolerance) return true
        val exp = lampExpected(value, cfg)
        if (lamp == LampState.HIGH) return exp == LampState.NORMAL
        return lamp == exp
    }

    fun fuse(a: NeedleResult?, b: NeedleResult?, lamp: String, cfg: MonitorConfig): Fused {
        val notes = mutableListOf<String>()
        val aOk = a?.value != null && a.confidence >= cfg.minConfidence
        val bOk = b?.value != null && b.confidence >= cfg.minConfidence
        var value: Double?
        var conf: Double
        var source: String
        val needlesAgree: Boolean
        if (aOk && bOk) {
            val diff = abs(b!!.value!! - a!!.value!!)
            needlesAgree = diff <= cfg.agreeTolerance
            value = b.value; source = "stage_b"
            if (needlesAgree) {
                // confidence-weighted mean of both methods (same as fusion.py)
                value = (a.confidence * a.value + b.confidence * b.value) / (a.confidence + b.confidence)
                source = "a+b"
                conf = 1.0 - (1.0 - a.confidence) * (1.0 - b.confidence)
            } else {
                conf = 0.5 * minOf(a.confidence, b.confidence)
                notes += "needle methods disagree by ${"%.2f".format(diff)}"
            }
        } else if (aOk || bOk) {
            val r = if (bOk) b!! else a!!
            value = r.value; source = r.method; conf = r.confidence
            needlesAgree = true
            notes += "single method ($source)"
        } else {
            val best = listOfNotNull(b, a).filter { it.value != null }.maxByOrNull { it.confidence }
            value = best?.value; conf = best?.confidence ?: 0.0; source = best?.method ?: "none"
            needlesAgree = false
            notes += "no confident needle reading"
        }

        val lOk = lampConsistent(value, lamp, cfg)
        if (!lOk) {
            notes += "lamp $lamp contradicts needle $value"
            conf *= 0.5
        }
        if (lamp == LampState.OFF || lamp == LampState.CONFLICT) notes += "lamp state $lamp"

        val agree = needlesAgree && lOk
        val status = when {
            value == null || conf < cfg.minConfidence || !agree || lamp == LampState.CONFLICT -> Status.UNCERTAIN
            value < cfg.criticalThreshold -> Status.CRITICAL
            value < cfg.lowThreshold -> Status.LOW
            else -> Status.OK
        }
        return Fused(value?.let { round3(it) }, round3(conf), agree, lOk, status, source, notes)
    }

    fun round3(x: Double) = Math.round(x * 1000.0) / 1000.0
}
