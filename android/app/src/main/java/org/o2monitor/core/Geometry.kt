package org.o2monitor.core

import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

/**
 * Port of vision/o2gauge/geometry.py.
 * Dial angle = degrees CLOCKWISE from 12 o'clock in [0, 360), image y axis pointing down.
 */
object Geometry {
    const val EDGE_TOL_DEG = 4.0

    fun dialAngle(cx: Double, cy: Double, px: Double, py: Double): Double {
        val a = Math.toDegrees(atan2(px - cx, -(py - cy)))
        return mod360(a)
    }

    fun pointAt(cx: Double, cy: Double, angleDeg: Double, r: Double): Pair<Double, Double> {
        val t = Math.toRadians(angleDeg)
        return Pair(cx + r * sin(t), cy - r * cos(t))
    }

    fun mod360(a: Double): Double {
        val m = a % 360.0
        return if (m < 0) m + 360.0 else m
    }
}

data class Scale(
    val zeroAngle: Double,
    val maxAngle: Double,
    val minValue: Double = 0.0,
    val maxValue: Double = 16.0,
    val direction: String = "cw",
) {
    val sweep: Double
        get() {
            val s = if (direction == "cw") Geometry.mod360(maxAngle - zeroAngle) else Geometry.mod360(zeroAngle - maxAngle)
            return if (s > 1e-9) s else 360.0
        }

    fun rel(angle: Double): Double =
        if (direction == "cw") Geometry.mod360(angle - zeroAngle) else Geometry.mod360(zeroAngle - angle)

    /** (value, inRange). Same clamping rules as Python Scale.value. */
    fun value(angle: Double, edgeTol: Double = Geometry.EDGE_TOL_DEG): Pair<Double, Boolean> {
        val rel = rel(angle)
        val sweep = sweep
        val frac: Double
        val inRange: Boolean
        if (rel <= sweep) {
            frac = rel / sweep
            inRange = true
        } else {
            val gap = 360.0 - sweep
            val pastMax = rel - sweep
            val beforeZero = 360.0 - rel
            if (pastMax < gap / 2.0) {
                frac = 1.0; inRange = pastMax <= edgeTol
            } else {
                frac = 0.0; inRange = beforeZero <= edgeTol
            }
        }
        return Pair(minValue + frac * (maxValue - minValue), inRange)
    }

    fun angle(value: Double): Double {
        val d = (value - minValue) / (maxValue - minValue) * sweep
        return if (direction == "cw") Geometry.mod360(zeroAngle + d) else Geometry.mod360(zeroAngle - d)
    }

    companion object {
        fun fromPoints(
            cx: Double, cy: Double, zx: Double, zy: Double, mx: Double, my: Double,
            minValue: Double, maxValue: Double, direction: String,
        ) = Scale(
            Geometry.dialAngle(cx, cy, zx, zy), Geometry.dialAngle(cx, cy, mx, my), minValue, maxValue, direction,
        )
    }
}
