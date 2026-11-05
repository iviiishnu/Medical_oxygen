package org.o2monitor.vision

import org.o2monitor.core.LampState

/** Port of vision/o2gauge/lamps.py. */
object LampReader {
    data class Params(
        val minVRel: Double = 0.8,
        val minVFloor: Int = 60,
        val minVCap: Int = 190,
        val minS: Int = 70,
        val whiteV: Int = 235,
        val whiteMaxS: Int = 60,
        val litFrac: Double = 0.12,
        val litFracWithCore: Double = 0.05,
        val coreFrac: Double = 0.15,
        val haloFrac: Double = 0.10,
        val relativeMargin: Double = 3.0,
    )

    data class Score(val lit: Boolean, val colored: Double, val core: Double, val score: Double, val valid: Boolean)

    private val HUES = mapOf(
        "red" to listOf(0..10, 160..179),
        "amber" to listOf(11..35),
        "green" to listOf(36..95),
    )

    fun frameMedianV(img: RgbImage): Double {
        val px = ImgOps.gridSample(img, 64)
        val hsv = IntArray(3)
        val v = DoubleArray(px.size) { ImgOps.hsv(px[it], hsv); hsv[2].toDouble() }
        return ImgOps.median(v)
    }

    fun minVFor(frameV: Double, p: Params) = minOf(maxOf(p.minVRel * frameV, p.minVFloor.toDouble()), p.minVCap.toDouble())

    fun score(img: RgbImage, box: List<Int>, hue: String, p: Params, frameV: Double): Score {
        val minV = minVFor(frameV, p)
        val x0 = maxOf(0, box[0]); val y0 = maxOf(0, box[1])
        val x1 = minOf(img.width, box[0] + box[2]); val y1 = minOf(img.height, box[1] + box[3])
        if (x1 <= x0 || y1 <= y0) return Score(false, 0.0, 0.0, 0.0, false)
        val ranges = HUES.getValue(hue)
        val hsv = IntArray(3)
        var col = 0; var core = 0
        for (y in y0 until y1) for (x in x0 until x1) {
            ImgOps.hsv(img.argb[y * img.width + x], hsv)
            val inHue = ranges.any { hsv[0] in it }
            if (inHue && hsv[1] >= p.minS && hsv[2] >= minV) col++
            if (hsv[2] >= p.whiteV && hsv[1] <= p.whiteMaxS) core++
        }
        val n = ((x1 - x0) * (y1 - y0)).toDouble()
        val colored = col / n; val c = core / n
        // blown-out white core: look for the lamp's colour in the glow ring around the box
        var halo = 0.0
        if (c >= p.coreFrac) {
            val w = box[2]; val h = box[3]
            val hx0 = maxOf(0, box[0] - w / 2); val hy0 = maxOf(0, box[1] - h / 2)
            val hx1 = minOf(img.width, box[0] + w + w / 2); val hy1 = minOf(img.height, box[1] + h + h / 2)
            var ring = 0; var hit = 0
            for (y in hy0 until hy1) for (x in hx0 until hx1) {
                if (x in x0 until x1 && y in y0 until y1) continue
                ring++
                ImgOps.hsv(img.argb[y * img.width + x], hsv)
                if (ranges.any { hsv[0] in it } && hsv[1] >= p.minS && hsv[2] >= minV) hit++
            }
            if (ring > 0) halo = hit.toDouble() / ring
        }
        val lit = colored >= p.litFrac || (colored >= p.litFracWithCore && c >= p.coreFrac) ||
            (c >= p.coreFrac && halo >= p.haloFrac)
        return Score(lit, colored, c, colored + c + halo, true)
    }

    fun combine(details: Map<String, Score>, p: Params): String {
        val lit = details.filterValues { it.lit }.keys.toList()
        if (lit.size == 1) return lit[0]
        if (lit.isEmpty()) return LampState.OFF
        val ranked = lit.sortedByDescending { details.getValue(it).score }
        val best = details.getValue(ranked[0]).score
        val second = details.getValue(ranked[1]).score
        return if (best >= p.relativeMargin * maxOf(second, 1e-6)) ranked[0] else LampState.CONFLICT
    }

    fun read(img: RgbImage, cal: Calibration, p: Params = Params()): Pair<String, Map<String, Score>> {
        if (cal.lamps.isEmpty()) return Pair(LampState.UNKNOWN, emptyMap())
        val fv = frameMedianV(img)
        val details = cal.lamps.associate { it.name to score(img, it.box, it.hue, p, fv) }
        return Pair(combine(details, p), details)
    }
}
