package org.o2monitor.vision

import org.o2monitor.core.Geometry
import org.o2monitor.core.NeedleResult
import org.o2monitor.core.Scale
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/** Port of vision/o2gauge/stage_a.py (see that file for the method). */
object StageA {
    const val N_RAYS = 720
    const val N_RINGS = 48
    const val SMOOTH_SIGMA_BINS = 2.0
    const val PEAK_EXCLUDE_DEG = 12
    const val MIN_LOCAL_MEAN = 16f

    fun frameQuality(img: RgbImage): String? {
        val px = ImgOps.gridSample(img, 64)
        var sum = 0.0
        val g = DoubleArray(px.size) { ImgOps.grayOf(px[it]).toDouble() }
        for (v in g) sum += v
        val mean = sum / g.size
        var ss = 0.0
        for (v in g) ss += (v - mean) * (v - mean)
        val std = sqrt(ss / g.size)
        if (mean < 25) return "frame_too_dark"
        if (mean > 245 && std < 8) return "frame_blown_out"
        if (std < 6) return "frame_uniform_camera_blocked"
        return null
    }

    fun blurKernel(radius: Double): Int = maxOf(5, (Math.round(0.2 * radius).toInt()) or 1)

    fun needleMap(crop: RgbImage, color: String, k: Int): Plane {
        val out = Plane(crop.width, crop.height)
        if (color == "red") {
            val hsv = IntArray(3)
            for (i in crop.argb.indices) {
                ImgOps.hsv(crop.argb[i], hsv)
                val red = if (hsv[0] <= 10 || hsv[0] >= 165) 1f else 0f
                out.data[i] = red * (hsv[1] / 255f) * minOf(hsv[2] / 120f, 1f)
            }
            return out
        }
        val gray = ImgOps.toGray(crop)
        val mean = ImgOps.boxBlur(gray, k)
        for (i in out.data.indices) {
            val m = mean.data[i]
            out.data[i] = ((m - gray.data[i]) / maxOf(m, MIN_LOCAL_MEAN)).coerceIn(0f, 1f)
        }
        return out
    }

    data class Geo(val cx: Double, val cy: Double, val scale: Scale, val radius: Double, val minv: DoubleArray?)

    fun geometry(cal: Calibration): Geo {
        val rect = cal.rectification() ?: return Geo(cal.center[0], cal.center[1], cal.scale(), cal.radius, null)
        val (m, rimRadius) = rect
        val (cx, cy) = Affine.apply(m, cal.center[0], cal.center[1])
        val (zx, zy) = Affine.apply(m, cal.zeroPoint[0], cal.zeroPoint[1])
        val (mx, my) = Affine.apply(m, cal.maxPoint[0], cal.maxPoint[1])
        val scale = Scale.fromPoints(cx, cy, zx, zy, mx, my, cal.minValue, cal.maxValue, cal.direction)
        return Geo(cx, cy, scale, rimRadius, Affine.invert(m))
    }

    /** Polar profile (one value per ray) or null if the dial is outside the frame. */
    fun polarProfile(img: RgbImage, cal: Calibration, geo: Geo = geometry(cal)): DoubleArray? {
        val n = N_RAYS * N_RINGS
        val xs = DoubleArray(n); val ys = DoubleArray(n)
        val rIn = cal.needleRInner * geo.radius; val rOut = cal.needleROuter * geo.radius
        for (j in 0 until N_RAYS) {
            val t = Math.toRadians(j * (360.0 / N_RAYS))
            val st = sin(t); val ct = cos(t)
            for (i in 0 until N_RINGS) {
                val rr = rIn + (rOut - rIn) * i / (N_RINGS - 1)     // == np.linspace
                var x = geo.cx + rr * st
                var y = geo.cy - rr * ct
                val mi = geo.minv
                if (mi != null) {
                    val p = Affine.apply(mi, x, y); x = p.first; y = p.second
                }
                xs[j * N_RINGS + i] = x; ys[j * N_RINGS + i] = y
            }
        }
        val k = blurKernel(cal.radius)
        val pad = k + 2
        val x0 = maxOf(0, floor(xs.min()).toInt() - pad)
        val y0 = maxOf(0, floor(ys.min()).toInt() - pad)
        val x1 = minOf(img.width, ceil(xs.max()).toInt() + pad + 1)
        val y1 = minOf(img.height, ceil(ys.max()).toInt() + pad + 1)
        if (x1 - x0 < 8 || y1 - y0 < 8) return null
        val nmap = needleMap(img.crop(x0, y0, x1, y1), cal.needleColor, k)

        val polar = FloatArray(n)
        for (q in 0 until n) polar[q] = ImgOps.bilinear(nmap, xs[q] - x0, ys[q] - y0)
        // per-ring median subtraction
        val col = FloatArray(N_RAYS)
        for (i in 0 until N_RINGS) {
            for (j in 0 until N_RAYS) col[j] = polar[j * N_RINGS + i]
            val med = medianF(col)
            for (j in 0 until N_RAYS) polar[j * N_RINGS + i] -= med
        }
        // per-ray median over the band
        val row = FloatArray(N_RINGS)
        return DoubleArray(N_RAYS) { j ->
            System.arraycopy(polar, j * N_RINGS, row, 0, N_RINGS)
            medianF(row).toDouble()
        }
    }

    private fun medianF(xs: FloatArray): Float {
        val s = xs.copyOf(); s.sort()
        val n = s.size
        return if (n % 2 == 1) s[n / 2] else (s[n / 2 - 1] + s[n / 2]) / 2f
    }

    fun circularSmooth(p: DoubleArray, sigma: Double = SMOOTH_SIGMA_BINS): DoubleArray {
        val k = ceil(sigma * 3).toInt()
        val ker = DoubleArray(2 * k + 1) { exp(-0.5 * ((it - k) / sigma) * ((it - k) / sigma)) }
        val s = ker.sum()
        for (i in ker.indices) ker[i] /= s
        val n = p.size
        // np.convolve(padded, ker, 'valid') == correlation with the reversed kernel (symmetric here)
        return DoubleArray(n) { i ->
            var acc = 0.0
            for (t in -k..k) acc += p[((i + t) % n + n) % n] * ker[k - t]
            acc
        }
    }

    /** (angleDeg, confidence). */
    fun findPeak(profile: DoubleArray): Pair<Double, Double> {
        val sm = circularSmooth(profile)
        var j = 0
        for (i in sm.indices) if (sm[i] > sm[j]) j = i
        val y0 = sm[(j - 1 + N_RAYS) % N_RAYS]; val y1 = sm[j]; val y2 = sm[(j + 1) % N_RAYS]
        val denom = y0 - 2 * y1 + y2
        val off = (if (kotlin.math.abs(denom) > 1e-12) 0.5 * (y0 - y2) / denom else 0.0).coerceIn(-0.5, 0.5)
        val angle = Geometry.mod360((j + off) * 360.0 / N_RAYS)

        val med = ImgOps.median(sm)
        val mad = ImgOps.median(DoubleArray(sm.size) { kotlin.math.abs(sm[it] - med) }) * 1.4826 + 1e-4
        val peak = sm[j] - med
        val z = peak / mad
        val excl = PEAK_EXCLUDE_DEG * N_RAYS / 360
        var second = Double.NEGATIVE_INFINITY
        for (i in sm.indices) {
            val d = minOf(((i - j) % N_RAYS + N_RAYS) % N_RAYS, ((j - i) % N_RAYS + N_RAYS) % N_RAYS)
            if (d > excl && sm[i] > second) second = sm[i]
        }
        second -= med
        val uniqueness = if (peak > 0) 1.0 - maxOf(second, 0.0) / peak else 0.0
        val confZ = ((z - 4.0) / 8.0).coerceIn(0.0, 1.0)
        val confSep = (uniqueness * 2.0).coerceIn(0.0, 1.0)
        val confAbs = (peak / 0.12).coerceIn(0.0, 1.0)
        return Pair(angle, confZ * confSep * confAbs)
    }

    fun read(img: RgbImage, cal: Calibration): NeedleResult {
        frameQuality(img)?.let { return NeedleResult(null, null, 0.0, false, reason = it) }
        val geo = geometry(cal)
        val prof = polarProfile(img, cal, geo)
            ?: return NeedleResult(null, null, 0.0, false, reason = "dial_outside_frame")
        var (angle, conf) = findPeak(prof)
        val (value, inRange) = geo.scale.value(angle)
        if (!inRange) conf *= 0.5
        return NeedleResult(
            round(value, 3), round(angle, 2), round(conf, 3), inRange,
            reason = if (conf > 0) "" else "no_needle_peak",
        )
    }

    private fun round(x: Double, d: Int): Double {
        val f = Math.pow(10.0, d.toDouble())
        return (x * f).roundToInt() / f
    }
}
