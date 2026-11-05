package org.o2monitor

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.o2monitor.core.Geometry
import org.o2monitor.core.Scale
import org.o2monitor.vision.Calibration
import org.o2monitor.vision.EllipseFit
import org.o2monitor.vision.LampReader
import org.o2monitor.vision.StageA
import java.io.File
import kotlin.math.abs

/** Kotlin Stage A + lamp reader must reproduce the Python reference (contract/parity). */
class VisionParityTest {
    private val dir = TestFiles.contract("parity")
    private val cases = Json.parseToJsonElement(File(dir, "expected.json").readText()).jsonArray.map { it.jsonObject }

    @Test
    fun stageAAndLampsMatchPython() {
        assertTrue(cases.size >= 20)
        val problems = mutableListOf<String>()
        var worst = 0.0
        for (c in cases) {
            val file = c["file"]!!.jsonPrimitive.content
            val cal = Calibration.fromJson(c["calibration"].toString())
            val img = TestFiles.loadImage(File(dir, file))
            val r = StageA.read(img, cal)
            val expV = c["value"]!!.jsonPrimitive.doubleOrNull
            val expConf = c["confidence"]!!.jsonPrimitive.doubleOrNull!!
            if (expV == null) {
                if (r.value != null) problems += "$file: expected unreadable, got ${r.value}"
            } else {
                val d = abs((r.value ?: Double.NaN) - expV)
                if (!(d <= 0.05)) problems += "$file: value ${r.value} vs python $expV"
                worst = maxOf(worst, if (d.isNaN()) 99.0 else d)
                if (abs(r.confidence - expConf) > 0.05) problems += "$file: conf ${r.confidence} vs $expConf"
            }
            val lamp = LampReader.read(img, cal).first
            val expLamp = c["lamp_state"]!!.jsonPrimitive.content
            if (lamp != expLamp) problems += "$file: lamp $lamp vs $expLamp"
        }
        println("worst |kotlin - python| = $worst over ${cases.size} cases")
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
    }

    @Test
    fun geometryBasics() {
        assertEquals(0.0, Geometry.dialAngle(0.0, 0.0, 0.0, -1.0), 1e-9)
        assertEquals(90.0, Geometry.dialAngle(0.0, 0.0, 1.0, 0.0), 1e-9)
        val s = Scale(225.0, 135.0, 0.0, 16.0)
        assertEquals(270.0, s.sweep, 1e-9)
        assertEquals(8.0, s.value(0.0).first, 1e-9)
        assertEquals(Pair(16.0, true), s.value(137.0))      // on the stop pin
        assertEquals(Pair(16.0, false), s.value(150.0))     // deep in the dead zone
        assertEquals(Pair(0.0, false), s.value(210.0))
    }

    @Test
    fun ellipseFitRecoversKnownEllipse() {
        val xs = DoubleArray(12) { 300 + 120 * kotlin.math.cos(it * Math.PI / 6) }
        val ys = DoubleArray(12) { 200 + 80 * kotlin.math.sin(it * Math.PI / 6) }
        val e = EllipseFit.fit(xs, ys)!!
        assertEquals(300.0, e.cx, 1e-6); assertEquals(200.0, e.cy, 1e-6)
        assertEquals(240.0, e.major, 1e-6); assertEquals(160.0, e.minor, 1e-6)
        assertEquals(0.0, Geometry.mod360(e.angleDeg + 360) % 180, 1e-6)
    }

    @Test
    fun blockedFrameUnreadable() {
        val c = cases.first { it["file"]!!.jsonPrimitive.content.endsWith("blocked.png") }
        val cal = Calibration.fromJson(c["calibration"].toString())
        val img = TestFiles.loadImage(File(dir, c["file"]!!.jsonPrimitive.content))
        assertNull(StageA.read(img, cal).value)
    }
}
