package org.o2monitor

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.o2monitor.vision.Calibration
import org.o2monitor.vision.TFLiteKeypointModel
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

/**
 * Stage B on the JVM: everything except the interpreter itself.
 *  - crop: Kotlin cropPixels() vs the exact Python model input (PNG)
 *  - decode + post-processing of the RAW TFLite output (from Python/LiteRT) vs Python's value
 * The interpreter itself is covered by the instrumented test (androidTest) on a device.
 */
class StageBParityTest {
    private val dir = TestFiles.contract("parity/stageb")
    private val cases = Json.parseToJsonElement(File(dir, "expected.json").readText()).jsonArray.map { it.jsonObject }

    @Test
    fun cropMatchesPython() {
        // OpenCV's warpAffine uses 1/32-pixel fixed-point weights, we use exact bilinear:
        // a few grey levels on single pixels, ~0 on average. Both are checked.
        var worst = 0
        var sum = 0L
        var n = 0L
        for (c in cases) {
            val name = c["case"]!!.jsonPrimitive.content
            val cal = Calibration.fromJson(c["calibration"].toString())
            val frame = TestFiles.loadImage(TestFiles.contract("parity/" + c["frame"]!!.jsonPrimitive.content))
            val ref = TestFiles.loadImage(File(dir, "${name}_crop.png"))
            val mine = TFLiteKeypointModel.cropPixels(frame, cal.center[0], cal.center[1], cal.radius, ref.width)
            for (i in mine.indices) for (sh in intArrayOf(16, 8, 0)) {
                val d = abs(((mine[i] shr sh) and 0xFF) - ((ref.argb[i] shr sh) and 0xFF))
                worst = maxOf(worst, d); sum += d; n++
            }
        }
        val mean = sum.toDouble() / n
        println("crop difference: worst $worst / 255, mean ${"%.3f".format(mean)}")
        assertTrue("crop worst pixel differs by $worst levels", worst <= 6)
        assertTrue("crop mean difference $mean", mean <= 0.5)
    }

    @Test
    fun decodeAndPostprocessMatchPython() {
        assertTrue(cases.size >= 6)
        for (c in cases) {
            val name = c["case"]!!.jsonPrimitive.content
            val shape = c["out_shape"]!!.jsonArray.map { it.jsonPrimitive.int }
            val bytes = File(dir, "${name}_out.bin").readBytes()
            val fb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
            val out = Array(shape[0]) { FloatArray(shape[1]) }
            for (r in 0 until shape[0]) fb.get(out[r])
            val (det, k) = TFLiteKeypointModel.decode(out, 320)!!
            val cal = Calibration.fromJson(c["calibration"].toString())
            val r = TFLiteKeypointModel.postprocess(det, k, cal, 320)
            val expV = c["value"]!!.jsonPrimitive.double
            val expC = c["confidence"]!!.jsonPrimitive.double
            assertEquals("$name value", expV, r.value!!, 0.01)
            assertEquals("$name confidence", expC, r.confidence, 0.01)
        }
    }
}
