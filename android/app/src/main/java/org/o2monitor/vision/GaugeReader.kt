package org.o2monitor.vision

import org.o2monitor.core.Fused
import org.o2monitor.core.Fusion
import org.o2monitor.core.LampState
import org.o2monitor.core.MonitorConfig
import org.o2monitor.core.NeedleResult
import org.o2monitor.core.Reading
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlin.math.max
import kotlin.random.Random

/** One processed frame. */
data class FrameResult(
    val reading: Reading,
    val stageA: NeedleResult?,
    val stageB: NeedleResult?,
    val fused: Fused?,
    val inferenceMs: Double,
)

/** Pluggable reader: camera frame (or nothing, for the fake) -> reading. */
interface GaugeReader {
    val name: String
    fun read(frame: RgbImage?, epochMs: Long): FrameResult
    fun close() {}
}

object Timestamps {
    val IST: ZoneOffset = ZoneOffset.ofHoursMinutes(5, 30)
    private val FMT = DateTimeFormatter.ISO_OFFSET_DATE_TIME
    fun iso(epochMs: Long): String =
        OffsetDateTime.ofInstant(java.time.Instant.ofEpochMilli(epochMs), IST).withNano(0).format(FMT)
}

/** Interface for Stage B (keypoint model); implemented by TFLiteKeypointModel. */
fun interface StageB {
    fun read(frame: RgbImage, cal: Calibration): NeedleResult
}

/** The real reader: Stage A + optional Stage B + lamps -> fusion. */
class CameraGaugeReader(
    private val cal: Calibration,
    private val cfg: MonitorConfig,
    private val stageB: StageB? = null,
) : GaugeReader {
    override val name = if (stageB != null) "camera+model" else "camera(stage A)"

    override fun read(frame: RgbImage?, epochMs: Long): FrameResult {
        val t0 = System.nanoTime()
        if (frame == null) {
            val r = Reading(cal.deviceId, cal.gaugeId, Timestamps.iso(epochMs), null, cal.unit, 0.0,
                LampState.UNKNOWN, false, "UNCERTAIN")
            return FrameResult(r, null, null, null, 0.0)
        }
        val a = StageA.read(frame, cal)
        val b = try { stageB?.read(frame, cal) } catch (e: Exception) {
            NeedleResult(null, null, 0.0, false, "stage_b", "model_error: ${e.message}")
        }
        val lamp = LampReader.read(frame, cal).first
        val f = Fusion.fuse(a, b, lamp, cfg)
        val ms = (System.nanoTime() - t0) / 1e6
        val r = Reading(cal.deviceId, cal.gaugeId, Timestamps.iso(epochMs), f.value, cal.unit, f.confidence,
            lamp, f.methodAgree, f.status)
        return FrameResult(r, a, b, f, ms)
    }
}

/**
 * Realistic fake readings for building/testing the app without a gauge.
 * Scenarios: steady, slow leak, sudden drop, unreadable frames, lamp low,
 * glare spikes (single wild frames), recovery.
 */
class FakeGaugeReader(
    private val cfg: MonitorConfig,
    var scenario: Scenario = Scenario.STEADY,
    private val deviceId: String = "tab-main-o2-01",
    private val gaugeId: String = "oxygen_main",
    seed: Int = 42,
    private val nominal: Double = 5.4,
) : GaugeReader {
    enum class Scenario { STEADY, SLOW_LEAK, SUDDEN_DROP, UNREADABLE, LAMP_LOW, GLARE_SPIKES, RECOVERY }

    override val name get() = "fake(${scenario.name.lowercase()})"
    private val rnd = Random(seed)
    private var startMs: Long? = null
    private var lastScenario = scenario

    override fun read(frame: RgbImage?, epochMs: Long): FrameResult {
        if (startMs == null || scenario != lastScenario) { startMs = epochMs; lastScenario = scenario }
        val t = (epochMs - startMs!!) / 1000.0
        val noise = rnd.nextDouble(-0.03, 0.03)
        var value: Double? = when (scenario) {
            Scenario.STEADY, Scenario.LAMP_LOW, Scenario.GLARE_SPIKES -> nominal + noise
            Scenario.SLOW_LEAK -> max(0.0, nominal - 0.01 * t) + noise          // 0.6 kg/cm2 per minute
            Scenario.SUDDEN_DROP -> (if (t < 10) nominal else 2.2) + noise
            Scenario.RECOVERY -> (if (t < 20) 2.8 else nominal) + noise
            Scenario.UNREADABLE -> null
        }
        var conf = if (value == null) 0.0 else 0.9 + rnd.nextDouble(0.0, 0.09)
        var agree = value != null
        // the panel lamp follows the TRUE pressure, not what a glare frame makes the needle look like
        val trueValue = value
        val lamp = when {
            scenario == Scenario.LAMP_LOW -> LampState.LOW
            trueValue == null -> LampState.UNKNOWN
            trueValue < (cfg.lampLowSetpoint ?: cfg.lowThreshold) -> LampState.LOW
            else -> LampState.NORMAL
        }
        if (scenario == Scenario.GLARE_SPIKES && rnd.nextDouble() < 0.1) {
            value = rnd.nextDouble(0.0, 16.0); conf = 0.35; agree = false        // glare frame
        }
        if (scenario == Scenario.LAMP_LOW) agree = false
        val status = when {
            value == null || conf < cfg.minConfidence || !agree -> "UNCERTAIN"
            value < cfg.criticalThreshold -> "CRITICAL"
            value < cfg.lowThreshold -> "LOW"
            else -> "OK"
        }
        val r = Reading(deviceId, gaugeId, Timestamps.iso(epochMs), value?.let { Fusion.round3(it) }, "kg/cm2",
            Fusion.round3(conf), lamp, agree, status)
        return FrameResult(r, null, null, null, 0.1)
    }
}
