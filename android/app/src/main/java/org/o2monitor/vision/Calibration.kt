package org.o2monitor.vision

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.o2monitor.core.Scale
import kotlin.math.abs
import kotlin.math.hypot

/** Same JSON as vision/o2gauge/calibration.py (written by either calibration tool). */
@Serializable
data class Lamp(val name: String, val box: List<Int>, val hue: String = "green")

@Serializable
data class Calibration(
    val center: List<Double>,
    val radius: Double,
    @SerialName("zero_point") val zeroPoint: List<Double>,
    @SerialName("max_point") val maxPoint: List<Double>,
    @SerialName("min_value") val minValue: Double = 0.0,
    @SerialName("max_value") val maxValue: Double = 16.0,
    val direction: String = "cw",
    val unit: String = "kg/cm2",
    @SerialName("device_id") val deviceId: String = "tab-main-o2-01",
    @SerialName("gauge_id") val gaugeId: String = "oxygen_main",
    @SerialName("image_size") val imageSize: List<Int>? = null,
    @SerialName("rim_points") val rimPoints: List<List<Double>>? = null,
    @SerialName("needle_color") val needleColor: String = "dark",
    @SerialName("needle_r_inner") val needleRInner: Double = 0.30,
    @SerialName("needle_r_outer") val needleROuter: Double = 0.72,
    val lamps: List<Lamp> = emptyList(),
    val version: Int = 1,
) {
    fun validate(): Calibration {
        require(radius > 5) { "radius too small" }
        require(maxValue > minValue) { "max_value must be > min_value" }
        require(direction == "cw" || direction == "ccw") { "direction must be cw or ccw" }
        require(needleColor == "dark" || needleColor == "red") { "needle_color must be dark or red" }
        require(needleRInner >= 0 && needleRInner < needleROuter && needleROuter <= 1.0) { "bad needle band" }
        for (p in listOf(zeroPoint, maxPoint)) {
            require(hypot(p[0] - center[0], p[1] - center[1]) >= 0.2 * radius) {
                "zero/max mark too close to the centre - re-tap calibration"
            }
        }
        require(abs(scale().sweep) >= 30) { "zero and max marks are almost at the same angle" }
        require(lamps.map { it.name }.toSet().size == lamps.size) { "duplicate lamp names" }
        for (l in lamps) {
            require(l.hue in setOf("red", "green", "amber")) { "bad lamp hue ${l.hue}" }
            require(l.box.size == 4 && l.box[2] > 0 && l.box[3] > 0) { "bad lamp box for ${l.name}" }
        }
        require(rimPoints == null || rimPoints.size >= 5) { "rim_points needs at least 5 points" }
        return this
    }

    fun scale() = Scale.fromPoints(
        center[0], center[1], zeroPoint[0], zeroPoint[1], maxPoint[0], maxPoint[1], minValue, maxValue, direction,
    )

    /** (affine M as 6 doubles [a b tx; c d ty], rim radius in corrected frame) or null. */
    fun rectification(): Pair<DoubleArray, Double>? {
        val rp = rimPoints ?: return null
        if (rp.size < 5) return null
        val e = EllipseFit.fit(rp.map { it[0] }.toDoubleArray(), rp.map { it[1] }.toDoubleArray()) ?: return null
        return Pair(e.toCircleAffine(), e.major / 2.0)
    }

    fun toJson(): String = JSON.encodeToString(serializer(), this)

    companion object {
        val JSON = Json { ignoreUnknownKeys = false; encodeDefaults = true; explicitNulls = true }
        fun fromJson(s: String): Calibration = JSON.decodeFromString(serializer(), s).validate()
    }
}

/** Affine helpers. M = [m0 m1 m2; m3 m4 m5]. */
object Affine {
    fun apply(m: DoubleArray, x: Double, y: Double) =
        Pair(m[0] * x + m[1] * y + m[2], m[3] * x + m[4] * y + m[5])

    fun invert(m: DoubleArray): DoubleArray {
        val det = m[0] * m[4] - m[1] * m[3]
        require(abs(det) > 1e-12) { "singular affine" }
        val a = m[4] / det; val b = -m[1] / det; val c = -m[3] / det; val d = m[0] / det
        return doubleArrayOf(a, b, -(a * m[2] + b * m[5]), c, d, -(c * m[2] + d * m[5]))
    }
}

/**
 * Least-squares ellipse fit (Fitzgibbon direct method, the same idea as cv2.fitEllipse;
 * results agree to sub-pixel for well-spread rim points, which is all the rectification needs).
 */
data class Ellipse(val cx: Double, val cy: Double, val major: Double, val minor: Double, val angleDeg: Double) {
    /** Affine that stretches the minor axis so the ellipse becomes a circle of diameter `major`. */
    fun toCircleAffine(): DoubleArray {
        val t = Math.toRadians(angleDeg)
        val ux = kotlin.math.cos(t); val uy = kotlin.math.sin(t)    // major-axis direction
        val vx = -uy; val vy = ux                                    // minor-axis direction
        val k = major / minor - 1.0
        val s00 = 1 + k * vx * vx; val s01 = k * vx * vy
        val s10 = k * vx * vy; val s11 = 1 + k * vy * vy
        return doubleArrayOf(s00, s01, cx - (s00 * cx + s01 * cy), s10, s11, cy - (s10 * cx + s11 * cy))
    }
}

object EllipseFit {
    fun fit(xs: DoubleArray, ys: DoubleArray): Ellipse? {
        val n = xs.size
        if (n < 5) return null
        // normalise for numerical stability
        val mx = xs.average(); val my = ys.average()
        val sc = xs.indices.maxOf { maxOf(abs(xs[it] - mx), abs(ys[it] - my)) }.takeIf { it > 0 } ?: return null
        // scatter matrix of [x^2, xy, y^2, x, y, 1]
        val S = Array(6) { DoubleArray(6) }
        for (i in 0 until n) {
            val x = (xs[i] - mx) / sc; val y = (ys[i] - my) / sc
            val d = doubleArrayOf(x * x, x * y, y * y, x, y, 1.0)
            for (a in 0 until 6) for (b in 0 until 6) S[a][b] += d[a] * d[b]
        }
        // Fitzgibbon: solve via reduced 3x3 problem (Halir & Flusser)
        val S1 = Array(3) { a -> DoubleArray(3) { b -> S[a][b] } }
        val S2 = Array(3) { a -> DoubleArray(3) { b -> S[a][b + 3] } }
        val S3 = Array(3) { a -> DoubleArray(3) { b -> S[a + 3][b + 3] } }
        val S3inv = Mat3.inv(S3) ?: return null
        val T = Mat3.mul(Mat3.scale(Mat3.mul(S3inv, Mat3.transpose(S2)), -1.0), Mat3.eye())  // T = -S3^-1 S2^T
        val Mm = Mat3.add(S1, Mat3.mul(S2, T))
        // premultiply by inverse of constraint matrix C1 = [[0,0,2],[0,-1,0],[2,0,0]]
        val M = arrayOf(
            doubleArrayOf(Mm[2][0] / 2, Mm[2][1] / 2, Mm[2][2] / 2),
            doubleArrayOf(-Mm[1][0], -Mm[1][1], -Mm[1][2]),
            doubleArrayOf(Mm[0][0] / 2, Mm[0][1] / 2, Mm[0][2] / 2),
        )
        val a1 = Mat3.ellipseEigenvector(M) ?: return null
        val a2 = DoubleArray(3) { r -> (0 until 3).sumOf { c -> T[r][c] * a1[c] } }
        val A = a1[0]; val B = a1[1]; val C = a1[2]; val D = a2[0]; val E = a2[1]; val F = a2[2]
        // conic -> geometric parameters (normalised frame)
        val den = B * B - 4 * A * C
        if (den >= 0) return null
        val x0 = (2 * C * D - B * E) / den
        val y0 = (2 * A * E - B * D) / den
        // principal axes: theta and theta + 90 deg; measure both semi-axes directly
        val theta1 = 0.5 * kotlin.math.atan2(B, A - C)
        val r1 = semiAxisAlong(A, B, C, D, E, F, x0, y0, theta1)
        val r2 = semiAxisAlong(A, B, C, D, E, F, x0, y0, theta1 + Math.PI / 2)
        val theta = if (r1 >= r2) theta1 else theta1 + Math.PI / 2
        val semiMajor = maxOf(r1, r2); val semiMinor = minOf(r1, r2)
        if (semiMinor <= 0 || semiMajor.isNaN()) return null
        return Ellipse(
            cx = x0 * sc + mx, cy = y0 * sc + my,
            major = 2 * semiMajor * sc, minor = 2 * semiMinor * sc,
            angleDeg = Math.toDegrees(theta),
        )
    }

    /** Distance from centre to the conic along direction t. */
    private fun semiAxisAlong(A: Double, B: Double, C: Double, D: Double, E: Double, F: Double,
                              x0: Double, y0: Double, t: Double): Double {
        val ux = kotlin.math.cos(t); val uy = kotlin.math.sin(t)
        val q = A * ux * ux + B * ux * uy + C * uy * uy
        val f0 = A * x0 * x0 + B * x0 * y0 + C * y0 * y0 + D * x0 + E * y0 + F
        return kotlin.math.sqrt(abs(f0 / q))
    }
}

internal object Mat3 {
    fun eye() = Array(3) { i -> DoubleArray(3) { j -> if (i == j) 1.0 else 0.0 } }
    fun transpose(a: Array<DoubleArray>) = Array(3) { i -> DoubleArray(3) { j -> a[j][i] } }
    fun mul(a: Array<DoubleArray>, b: Array<DoubleArray>) =
        Array(3) { i -> DoubleArray(3) { j -> (0 until 3).sumOf { k -> a[i][k] * b[k][j] } } }
    fun add(a: Array<DoubleArray>, b: Array<DoubleArray>) = Array(3) { i -> DoubleArray(3) { j -> a[i][j] + b[i][j] } }
    fun scale(a: Array<DoubleArray>, s: Double) = Array(3) { i -> DoubleArray(3) { j -> a[i][j] * s } }
    fun det(a: Array<DoubleArray>) =
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) -
            a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) +
            a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])

    fun inv(a: Array<DoubleArray>): Array<DoubleArray>? {
        val d = det(a)
        if (abs(d) < 1e-18) return null
        val r = Array(3) { DoubleArray(3) }
        for (i in 0 until 3) for (j in 0 until 3) {
            val i1 = (j + 1) % 3; val i2 = (j + 2) % 3; val j1 = (i + 1) % 3; val j2 = (i + 2) % 3
            r[i][j] = (a[i1][j1] * a[i2][j2] - a[i1][j2] * a[i2][j1]) / d
        }
        return r
    }

    /** Eigenvector of the 3x3 matrix with 4ac - b^2 > 0 (the ellipse solution). */
    fun ellipseEigenvector(m: Array<DoubleArray>): DoubleArray? {
        // characteristic polynomial roots via the trigonometric/cardano method on a general 3x3
        val eig = realEigenvalues(m)
        for (lam in eig) {
            val v = nullVector(Array(3) { i -> DoubleArray(3) { j -> m[i][j] - if (i == j) lam else 0.0 } }) ?: continue
            if (4 * v[0] * v[2] - v[1] * v[1] > 0) return v
        }
        return null
    }

    private fun realEigenvalues(m: Array<DoubleArray>): List<Double> {
        val a = -(m[0][0] + m[1][1] + m[2][2])
        val b = m[0][0] * m[1][1] + m[0][0] * m[2][2] + m[1][1] * m[2][2] -
            m[0][1] * m[1][0] - m[0][2] * m[2][0] - m[1][2] * m[2][1]
        val c = -det(m)
        // x^3 + a x^2 + b x + c = 0
        val q = (3 * b - a * a) / 9
        val r = (9 * a * b - 27 * c - 2 * a * a * a) / 54
        val disc = q * q * q + r * r
        val out = mutableListOf<Double>()
        if (disc > 0) {
            val s = kotlin.math.cbrt(r + kotlin.math.sqrt(disc))
            val t = kotlin.math.cbrt(r - kotlin.math.sqrt(disc))
            out += s + t - a / 3
        } else {
            val th = kotlin.math.acos((r / kotlin.math.sqrt(-q * q * q)).coerceIn(-1.0, 1.0))
            val sq = 2 * kotlin.math.sqrt(-q)
            for (k in 0 until 3) out += sq * kotlin.math.cos((th + 2 * Math.PI * k) / 3) - a / 3
        }
        return out
    }

    private fun nullVector(m: Array<DoubleArray>): DoubleArray? {
        // cross product of the two most independent rows
        val rows = m.toList()
        var best: DoubleArray? = null
        var bestN = 0.0
        for (i in 0 until 3) for (j in i + 1 until 3) {
            val a = rows[i]; val b = rows[j]
            val v = doubleArrayOf(a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
            val nrm = kotlin.math.sqrt(v.sumOf { it * it })
            if (nrm > bestN) { bestN = nrm; best = v }
        }
        return best?.let { v -> DoubleArray(3) { v[it] / bestN } }
    }
}
