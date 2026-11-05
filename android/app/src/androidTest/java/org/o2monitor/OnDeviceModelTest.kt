package org.o2monitor

import android.graphics.BitmapFactory
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.o2monitor.vision.Calibration
import org.o2monitor.vision.FrameConvert
import org.o2monitor.vision.StageA
import org.o2monitor.vision.TFLiteKeypointModel
import kotlin.math.abs

/**
 * Runs on the real tablet:  gradlew connectedDebugAndroidTest
 * The REAL LiteRT model (GPU delegate if available) on the parity frames must match the Python
 * reference within 0.05 kg/cm2, and the full read must stay under 100 ms per frame.
 * Logcat tag "O2DeviceTest" prints timing and confidence for every frame.
 */
@RunWith(AndroidJUnit4::class)
class OnDeviceModelTest {
    private val testCtx = InstrumentationRegistry.getInstrumentation().context      // androidTest assets (contract/)
    private val appCtx = InstrumentationRegistry.getInstrumentation().targetContext  // app assets (model)

    private fun asset(path: String) = testCtx.assets.open(path).use { it.readBytes() }

    @Test
    fun modelMatchesPythonAndIsFastEnough() {
        val model = TFLiteKeypointModel.loadOrNull(appCtx)
        assertNotNull("gauge_pose.tflite missing from app assets", model)
        model!!
        val cases = Json.parseToJsonElement(String(asset("parity/stageb/expected.json"))).jsonArray.map { it.jsonObject }
        val problems = mutableListOf<String>()
        val times = mutableListOf<Double>()
        repeat(3) { // warm-up (GPU delegate compiles shaders on first runs)
            val c = cases[0]
            val bytes = asset("parity/" + c["frame"]!!.jsonPrimitive.content)
            val b = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            model.read(FrameConvert.fromBitmap(b), Calibration.fromJson(c["calibration"].toString()))
        }
        for (c in cases) {
            val bytes = asset("parity/" + c["frame"]!!.jsonPrimitive.content)
            val img = FrameConvert.fromBitmap(BitmapFactory.decodeByteArray(bytes, 0, bytes.size))
            val cal = Calibration.fromJson(c["calibration"].toString())
            val t0 = System.nanoTime()
            val a = StageA.read(img, cal)
            val r = model.read(img, cal)
            val ms = (System.nanoTime() - t0) / 1e6
            times += ms
            val exp = c["value"]!!.jsonPrimitive.double
            Log.i("O2DeviceTest", "${c["case"]}: B=${r.value} (conf ${r.confidence}) A=${a.value} python=$exp " +
                "total=${"%.1f".format(ms)} ms model=${"%.1f".format(model.lastMs)} ms delegate=${model.delegate}")
            if (r.value == null || abs(r.value!! - exp) > 0.05) problems += "${c["case"]}: ${r.value} vs $exp"
        }
        val median = times.sorted()[times.size / 2]
        Log.i("O2DeviceTest", "median Stage A + Stage B = ${"%.1f".format(median)} ms on ${model.delegate}")
        model.close()
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
        assertTrue("too slow: median $median ms", median <= 100.0)
    }
}
