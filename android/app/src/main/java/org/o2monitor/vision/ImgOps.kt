package org.o2monitor.vision

import kotlin.math.floor

/** ARGB_8888 pixels, row-major (same layout as Bitmap.getPixels). */
class RgbImage(val width: Int, val height: Int, val argb: IntArray) {
    init { require(argb.size == width * height) { "pixel count mismatch" } }

    fun crop(x0: Int, y0: Int, x1: Int, y1: Int): RgbImage {
        val w = x1 - x0; val h = y1 - y0
        val out = IntArray(w * h)
        for (y in 0 until h) System.arraycopy(argb, (y0 + y) * width + x0, out, y * w, w)
        return RgbImage(w, h, out)
    }
}

/** 2-D float plane. */
class Plane(val width: Int, val height: Int, val data: FloatArray = FloatArray(width * height)) {
    operator fun get(x: Int, y: Int) = data[y * width + x]
}

/** Port of vision/o2gauge/imgops.py - keep the two in lock-step. */
object ImgOps {
    fun r(p: Int) = (p shr 16) and 0xFF
    fun g(p: Int) = (p shr 8) and 0xFF
    fun b(p: Int) = p and 0xFF

    /** Fixed-point BT.601 luma == OpenCV BGR2GRAY. */
    fun grayOf(p: Int): Int = (r(p) * 4899 + g(p) * 9617 + b(p) * 1868 + 8192) shr 14

    fun toGray(img: RgbImage): Plane {
        val out = Plane(img.width, img.height)
        for (i in img.argb.indices) out.data[i] = grayOf(img.argb[i]).toFloat()
        return out
    }

    /** numpy 'reflect' (OpenCV BORDER_REFLECT_101) index for i in [-n+1, 2n-2]. */
    private fun reflect101(i: Int, n: Int): Int {
        if (n == 1) return 0
        var j = i
        while (j < 0 || j >= n) {
            j = if (j < 0) -j else 2 * (n - 1) - j
        }
        return j
    }

    /** k x k mean, reflect-101 borders (edge padding beyond one reflection for tiny images). */
    fun boxBlur(a: Plane, k: Int): Plane {
        val r = k / 2
        if (r == 0) return Plane(a.width, a.height, a.data.copyOf())
        val w = a.width; val h = a.height
        val ry = minOf(r, h - 1); val rx = minOf(r, w - 1)
        fun idx(i: Int, n: Int, re: Int): Int {
            // first reflect within re, then clamp (edge) for the remaining r - re
            val c = i.coerceIn(-re, n - 1 + re)
            return reflect101(c, n)
        }
        val pw = w + 2 * r; val ph = h + 2 * r
        // integral image in double precision (matches numpy float64 cumsum)
        val ii = DoubleArray((pw + 1) * (ph + 1))
        for (py in 0 until ph) {
            val sy = idx(py - r, h, ry)
            var rowSum = 0.0
            for (px in 0 until pw) {
                val sx = idx(px - r, w, rx)
                rowSum += a.data[sy * w + sx]
                ii[(py + 1) * (pw + 1) + px + 1] = ii[py * (pw + 1) + px + 1] + rowSum
            }
        }
        val out = Plane(w, h)
        val kk = (k * k).toDouble()
        for (y in 0 until h) for (x in 0 until w) {
            val s = ii[(y + k) * (pw + 1) + x + k] - ii[y * (pw + 1) + x + k] -
                ii[(y + k) * (pw + 1) + x] + ii[y * (pw + 1) + x]
            out.data[y * w + x] = (s / kk).toFloat()
        }
        return out
    }

    /** Bilinear sample; outside (x0+1 >= w etc.) returns 0, like imgops.bilinear. */
    fun bilinear(a: Plane, x: Double, y: Double): Float {
        val x0 = floor(x).toInt(); val y0 = floor(y).toInt()
        if (x0 < 0 || y0 < 0 || x0 + 1 >= a.width || y0 + 1 >= a.height) return 0f
        val fx = (x - x0).toFloat(); val fy = (y - y0).toFloat()
        val v00 = a[x0, y0]; val v01 = a[x0 + 1, y0]; val v10 = a[x0, y0 + 1]; val v11 = a[x0 + 1, y0 + 1]
        return (v00 * (1 - fx) + v01 * fx) * (1 - fy) + (v10 * (1 - fx) + v11 * fx) * fy
    }

    /** OpenCV-convention HSV (H 0-179, S/V 0-255) - same float formula as imgops.hsv. */
    fun hsv(p: Int, out: IntArray) {
        val rr = r(p).toFloat(); val gg = g(p).toFloat(); val bb = b(p).toFloat()
        val v = maxOf(rr, gg, bb)
        val mn = minOf(rr, gg, bb)
        val d = v - mn
        val s = if (v > 0) 255f * d / maxOf(v, 1e-6f) else 0f
        val dd = maxOf(d, 1e-6f)
        var h = when (v) {
            rr -> 60f * (gg - bb) / dd
            gg -> 120f + 60f * (bb - rr) / dd
            else -> 240f + 60f * (rr - gg) / dd
        }
        if (d == 0f) h = 0f
        if (h < 0) h += 360f
        out[0] = floor(h / 2f + 0.5f).toInt() % 180
        out[1] = floor(s + 0.5f).toInt()
        out[2] = v.toInt()
    }

    /** n x n grid of pixels at (i*h)/n, (j*w)/n. */
    fun gridSample(img: RgbImage, n: Int = 64): IntArray {
        val out = IntArray(n * n)
        for (i in 0 until n) {
            val y = (i * img.height) / n
            for (j in 0 until n) out[i * n + j] = img.argb[y * img.width + (j * img.width) / n]
        }
        return out
    }

    /** numpy.median semantics (mean of the two middle values for even counts). */
    fun median(xs: FloatArray, n: Int = xs.size): Double {
        val s = xs.copyOf(n); s.sort()
        return if (n % 2 == 1) s[n / 2].toDouble() else (s[n / 2 - 1].toDouble() + s[n / 2].toDouble()) / 2.0
    }

    fun median(xs: DoubleArray): Double {
        val s = xs.copyOf(); s.sort()
        val n = s.size
        return if (n % 2 == 1) s[n / 2] else (s[n / 2 - 1] + s[n / 2]) / 2.0
    }
}
