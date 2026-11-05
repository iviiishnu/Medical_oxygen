package org.o2monitor.vision

import android.graphics.Bitmap
import androidx.camera.core.ImageProxy

/** CameraX RGBA_8888 frames -> upright RgbImage, and back to Bitmap for preview/snapshots. */
object FrameConvert {
    fun fromImageProxy(img: ImageProxy): RgbImage {
        val plane = img.planes[0]
        val buf = plane.buffer
        val w = img.width; val h = img.height
        val rowStride = plane.rowStride; val px = plane.pixelStride
        val out = IntArray(w * h)
        val row = ByteArray(rowStride)
        buf.rewind()
        for (y in 0 until h) {
            buf.position(y * rowStride)
            buf.get(row, 0, minOf(rowStride, buf.remaining()))
            var o = y * w
            var i = 0
            for (x in 0 until w) {
                val r = row[i].toInt() and 0xFF
                val g = row[i + 1].toInt() and 0xFF
                val b = row[i + 2].toInt() and 0xFF
                out[o++] = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
                i += px
            }
        }
        return rotate(RgbImage(w, h, out), img.imageInfo.rotationDegrees)
    }

    fun rotate(src: RgbImage, degrees: Int): RgbImage {
        val d = ((degrees % 360) + 360) % 360
        if (d == 0) return src
        val w = src.width; val h = src.height
        return when (d) {
            90 -> { val o = IntArray(w * h); for (y in 0 until h) for (x in 0 until w) o[x * h + (h - 1 - y)] = src.argb[y * w + x]; RgbImage(h, w, o) }
            180 -> { val o = IntArray(w * h); for (i in 0 until w * h) o[w * h - 1 - i] = src.argb[i]; RgbImage(w, h, o) }
            270 -> { val o = IntArray(w * h); for (y in 0 until h) for (x in 0 until w) o[(w - 1 - x) * h + y] = src.argb[y * w + x]; RgbImage(h, w, o) }
            else -> src
        }
    }

    fun toBitmap(img: RgbImage, maxSide: Int = Int.MAX_VALUE): Bitmap {
        val b = Bitmap.createBitmap(img.argb, img.width, img.height, Bitmap.Config.ARGB_8888)
        val s = maxSide.toFloat() / maxOf(img.width, img.height)
        return if (s < 1f) Bitmap.createScaledBitmap(b, (img.width * s).toInt(), (img.height * s).toInt(), true) else b
    }

    fun fromBitmap(b: Bitmap): RgbImage {
        val px = IntArray(b.width * b.height)
        b.getPixels(px, 0, b.width, 0, 0, b.width, b.height)
        return RgbImage(b.width, b.height, px)
    }
}
