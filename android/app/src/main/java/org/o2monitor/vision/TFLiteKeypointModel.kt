package org.o2monitor.vision

import android.content.Context
import android.util.Log
import org.o2monitor.core.Geometry
import org.o2monitor.core.NeedleResult
import org.o2monitor.core.Scale
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.CompatibilityList
import org.tensorflow.lite.gpu.GpuDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel
import kotlin.math.floor
import kotlin.math.hypot

/**
 * Stage B on the tablet. Implements contract/stage_b_spec.md exactly:
 * crop around the calibrated dial -> 320x320 RGB/255 NHWC -> YOLO pose -> 4 keypoints -> value.
 * Uses the GPU delegate when the device supports it, else 4 CPU threads (XNNPACK).
 */
class TFLiteKeypointModel(model: ByteBuffer, useGpu: Boolean = true) : StageB, AutoCloseable {
    private var gpu: GpuDelegate? = null
    private val interp: Interpreter
    private val inShape: IntArray
    private val outShape: IntArray
    private val input: ByteBuffer
    private val output: Array<Array<FloatArray>>
    val delegate: String
    var lastMs = 0.0; private set

    init {
        val opts = Interpreter.Options()
        var d = "cpu x4"
        if (useGpu && runCatching { CompatibilityList().isDelegateSupportedOnThisDevice }.getOrDefault(false)) {
            runCatching { GpuDelegate(CompatibilityList().bestOptionsForThisDevice) }.onSuccess {
                gpu = it; opts.addDelegate(it); d = "gpu"
            }
        }
        if (gpu == null) opts.setNumThreads(4)
        interp = try { Interpreter(model, opts) } catch (e: Exception) {
            // some GPU drivers reject the graph at init time: fall back to CPU
            gpu?.close(); gpu = null; d = "cpu x4 (gpu failed)"
            Interpreter(model, Interpreter.Options().setNumThreads(4))
        }
        delegate = d
        inShape = interp.getInputTensor(0).shape()           // [1, 320, 320, 3]
        outShape = interp.getOutputTensor(0).shape()         // [1, 300, 18] (end-to-end) or [1, 17, N]
        input = ByteBuffer.allocateDirect(4 * inShape[1] * inShape[2] * 3).order(ByteOrder.nativeOrder())
        output = Array(outShape[0]) { Array(outShape[1]) { FloatArray(outShape[2]) } }
        Log.i(TAG, "model in=${inShape.toList()} out=${outShape.toList()} delegate=$delegate")
    }

    val size get() = inShape[1]

    fun fillInput(img: RgbImage, cx: Double, cy: Double, radius: Double) {
        input.rewind()
        for (p in cropPixels(img, cx, cy, radius, size)) {
            input.putFloat(((p shr 16) and 0xFF) / 255f)
            input.putFloat(((p shr 8) and 0xFF) / 255f)
            input.putFloat((p and 0xFF) / 255f)
        }
        input.rewind()
    }

    /** Raw inference on the prepared input: (detConf, keypoints [4][3] in input pixels). */
    fun run(): Pair<Double, Array<DoubleArray>>? {
        val t0 = System.nanoTime()
        interp.run(input, output)
        lastMs = (System.nanoTime() - t0) / 1e6
        return decode(output[0], size)
    }

    override fun read(frame: RgbImage, cal: Calibration): NeedleResult {
        val cx = cal.center[0]; val cy = cal.center[1]
        fillInput(frame, cx, cy, cal.radius)
        val (det, k) = run() ?: return NeedleResult(null, null, 0.0, false, "stage_b", "no_detection")
        return postprocess(det, k, cal, size)
    }

    override fun close() {
        interp.close()
        gpu?.close()
    }

    companion object {
        const val TAG = "TFLiteKeypointModel"
        const val CROP_SCALE = 1.4
        const val MAX_CENTER_OFFSET = 0.15
        const val ASSET = "gauge_pose.tflite"

        private fun r3(x: Double) = Math.round(x * 1000) / 1000.0

        /** Model input crop as ARGB pixels (bilinear, replicate border) - same as dataset.crop_affine/make_crop. */
        fun cropPixels(img: RgbImage, cx: Double, cy: Double, radius: Double, n: Int): IntArray {
            val s = n / (2 * CROP_SCALE * radius)
            val out = IntArray(n * n)
            for (oy in 0 until n) {
                val y = (oy - n / 2.0) / s + cy
                for (ox in 0 until n) out[oy * n + ox] = sampleReplicate(img, (ox - n / 2.0) / s + cx, y)
            }
            return out
        }

        /** Keypoints in input pixels -> NeedleResult (contract/stage_b_spec.md sections 3-5). */
        fun postprocess(det: Double, k: Array<DoubleArray>, cal: Calibration, size: Int): NeedleResult {
        val cx = cal.center[0]; val cy = cal.center[1]
        val s = size / (2 * CROP_SCALE * cal.radius)
        val raw = Array(4) { i -> doubleArrayOf((k[i][0] - size / 2.0) / s + cx, (k[i][1] - size / 2.0) / s + cy) }
        // zero / max: the tapped calibration marks (more precise than predicted; camera is fixed)
        raw[2] = doubleArrayOf(cal.zeroPoint[0], cal.zeroPoint[1])
        raw[3] = doubleArrayOf(cal.maxPoint[0], cal.maxPoint[1])
        // off-axis camera: measure angles in the perspective-corrected frame, like Stage A
        val m = cal.rectification()?.first
        val pts = if (m == null) raw else Array(4) { i ->
            Affine.apply(m, raw[i][0], raw[i][1]).let { doubleArrayOf(it.first, it.second) }
        }
        val (c, tip, zero, mx) = pts
        val scale = Scale.fromPoints(c[0], c[1], zero[0], zero[1], mx[0], mx[1], cal.minValue, cal.maxValue, cal.direction)
        val angle = Geometry.dialAngle(c[0], c[1], tip[0], tip[1])
        val (value, inRange) = scale.value(angle)
        var conf = det * minOf(k[0][2], k[1][2])
        val off = hypot(raw[0][0] - cx, raw[0][1] - cy) / cal.radius
        if (off > MAX_CENTER_OFFSET) conf *= maxOf(0.0, 1 - (off - MAX_CENTER_OFFSET) / MAX_CENTER_OFFSET)
        if (!inRange) conf = minOf(conf, StageA.DEAD_ZONE_MAX_CONF)
        return NeedleResult(r3(value), Math.round(angle * 100) / 100.0, r3(conf), inRange, "stage_b")
        }

        fun loadOrNull(ctx: Context): TFLiteKeypointModel? = try {
            val fd = ctx.assets.openFd(ASSET)
            val buf: MappedByteBuffer = FileInputStream(fd.fileDescriptor).channel
                .map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
            TFLiteKeypointModel(buf)
        } catch (e: Exception) {
            Log.w(TAG, "keypoint model not available, Stage A only: ${e.message}")
            null
        }

        fun sampleReplicate(img: RgbImage, x: Double, y: Double): Int {
            val xc = x.coerceIn(0.0, img.width - 1.0); val yc = y.coerceIn(0.0, img.height - 1.0)
            val x0 = floor(xc).toInt(); val y0 = floor(yc).toInt()
            val x1 = minOf(x0 + 1, img.width - 1); val y1 = minOf(y0 + 1, img.height - 1)
            val fx = xc - x0; val fy = yc - y0
            fun ch(p: Int, sh: Int) = ((p shr sh) and 0xFF).toDouble()
            val p00 = img.argb[y0 * img.width + x0]; val p01 = img.argb[y0 * img.width + x1]
            val p10 = img.argb[y1 * img.width + x0]; val p11 = img.argb[y1 * img.width + x1]
            var out = 0xFF shl 24
            for (sh in intArrayOf(16, 8, 0)) {
                val v = (ch(p00, sh) * (1 - fx) + ch(p01, sh) * fx) * (1 - fy) + (ch(p10, sh) * (1 - fx) + ch(p11, sh) * fx) * fy
                out = out or ((v + 0.5).toInt().coerceIn(0, 255) shl sh)
            }
            return out
        }

        /** Port of stage_b.decode(): both YOLO output layouts, coords possibly normalised. */
        fun decode(o: Array<FloatArray>, size: Int, nKpt: Int = 4): Pair<Double, Array<DoubleArray>>? {
            val e2eWidth = 6 + 3 * nKpt
            val classic = 5 + 3 * nKpt
            var best = -1; var bestConf = -1f
            val rows: Int; val get: (Int, Int) -> Float; val kOff: Int
            if (o[0].size == e2eWidth && o.size != classic) {           // [300][18]
                rows = o.size; get = { r, c -> o[r][c] }; kOff = 6
            } else if (o.size == classic) {                              // [17][N] channels first
                rows = o[0].size; get = { r, c -> o[c][r] }; kOff = 5
            } else if (o[0].size == classic) {                           // [N][17] rows
                rows = o.size; get = { r, c -> o[r][c] }; kOff = 5
            } else return null
            for (r in 0 until rows) { val c = get(r, 4); if (c > bestConf) { bestConf = c; best = r } }
            if (best < 0) return null
            val k = Array(nKpt) { i -> DoubleArray(3) { j -> get(best, kOff + 3 * i + j).toDouble() } }
            if (k.all { it[0] <= 1.5 && it[1] <= 1.5 }) for (p in k) { p[0] *= size; p[1] *= size }
            return Pair(bestConf.toDouble(), k)
        }
    }
}
