package org.o2monitor

import org.o2monitor.vision.RgbImage
import java.io.File
import javax.imageio.ImageIO

object TestFiles {
    val repoRoot: File = File(System.getProperty("repoRoot") ?: "../..").absoluteFile
    fun contract(name: String) = File(repoRoot, "contract/$name")

    fun loadImage(f: File): RgbImage {
        val bi = ImageIO.read(f) ?: error("cannot read $f")
        val px = IntArray(bi.width * bi.height)
        bi.getRGB(0, 0, bi.width, bi.height, px, 0, bi.width)
        return RgbImage(bi.width, bi.height, px)
    }
}
