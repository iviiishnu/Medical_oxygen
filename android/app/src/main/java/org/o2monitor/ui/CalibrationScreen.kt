package org.o2monitor.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.o2monitor.O2App
import org.o2monitor.monitor.MonitorBus
import org.o2monitor.monitor.MonitorService
import org.o2monitor.vision.Calibration
import org.o2monitor.vision.Lamp
import org.o2monitor.vision.LampReader
import org.o2monitor.vision.StageA
import kotlin.math.hypot

/** Panel presets: lamps + needle band measured on the real panels (counterweight tails!). */
data class PanelPreset(val label: String, val maxValue: Double, val lamps: List<Pair<String, String>>,
                       val rIn: Double, val rOut: Double)

val PRESETS = listOf(
    PanelPreset("Alarm box 0-16 (LOW / NORMAL)", 16.0, listOf("LOW" to "red", "NORMAL" to "green"), 0.55, 0.80),
    PanelPreset("Magnate O2 0-10 (HIGH / NORMAL / LOW)", 10.0,
        listOf("HIGH" to "amber", "NORMAL" to "green", "LOW" to "red"), 0.60, 0.90),
    PanelPreset("Gauge only (no lamps)", 16.0, emptyList(), 0.40, 0.80),
)

@Composable
fun CalibrationScreen(onDone: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = O2App.instance.prefs
    val frozen = remember { MonitorBus.preview.value }
    val full = remember { MonitorBus.lastFullFrame }
    val k = remember { MonitorBus.previewScale }
    var preset by remember { mutableStateOf(PRESETS[0]) }
    var maxText by remember { mutableStateOf(PRESETS[0].maxValue.toString()) }
    val taps = remember { mutableStateListOf<Offset>() }          // in FULL frame pixels
    var viewSize by remember { mutableStateOf(IntSize.Zero) }
    var result by remember { mutableStateOf<String?>(null) }

    val steps = buildList {
        add("Tap the CENTRE of the dial (needle pivot)")
        add("Tap a point on the dial RIM (edge of the white face)")
        add("Tap the 0 mark (start of the scale)")
        add("Tap the MAX mark (end of the scale)")
        for ((n, _) in preset.lamps) { add("$n lamp: tap TOP-LEFT of the lit area"); add("$n lamp: tap BOTTOM-RIGHT") }
    }

    fun build(): Calibration? = runCatching {
        if (taps.size < steps.size) return null
        val c = taps[0]
        val lamps = preset.lamps.mapIndexed { i, (n, hue) ->
            val a = taps[4 + 2 * i]; val b = taps[5 + 2 * i]
            Lamp(n, listOf(minOf(a.x, b.x).toInt(), minOf(a.y, b.y).toInt(),
                kotlin.math.abs(a.x - b.x).toInt(), kotlin.math.abs(a.y - b.y).toInt()), hue)
        }
        Calibration(
            center = listOf(c.x.toDouble(), c.y.toDouble()),
            radius = hypot((taps[1].x - c.x).toDouble(), (taps[1].y - c.y).toDouble()),
            zeroPoint = listOf(taps[2].x.toDouble(), taps[2].y.toDouble()),
            maxPoint = listOf(taps[3].x.toDouble(), taps[3].y.toDouble()),
            maxValue = maxText.toDoubleOrNull() ?: preset.maxValue,
            deviceId = prefs.deviceId, imageSize = full?.let { listOf(it.width, it.height) },
            needleRInner = preset.rIn, needleROuter = preset.rOut, lamps = lamps,
        ).validate()
    }.onFailure { result = "Invalid: ${it.message}" }.getOrNull()

    Surface(Modifier.fillMaxSize()) {
        if (frozen == null || full == null) {
            Column(Modifier.padding(24.dp)) {
                Text("No camera frame yet. Start monitoring in Camera mode, wait a few seconds, then open Calibrate.")
                Button(onClick = onDone) { Text("Back") }
            }
            return@Surface
        }
        Row(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f).fillMaxHeight().onSizeChanged { viewSize = it }
                .pointerInput(steps.size) {
                    detectTapGestures { p ->
                        if (taps.size >= steps.size || viewSize.width == 0) return@detectTapGestures
                        // ContentScale.Fit letterboxing
                        val s = minOf(viewSize.width / frozen.width.toFloat(), viewSize.height / frozen.height.toFloat())
                        val ox = (viewSize.width - frozen.width * s) / 2; val oy = (viewSize.height - frozen.height * s) / 2
                        val px = (p.x - ox) / s; val py = (p.y - oy) / s
                        if (px in 0f..frozen.width.toFloat() && py in 0f..frozen.height.toFloat()) {
                            taps.add(Offset(px * k, py * k)); result = null
                        }
                    }
                }) {
                Image(frozen.asImageBitmap(), "frame", Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                Canvas(Modifier.fillMaxSize()) {
                    val s = minOf(size.width / frozen.width, size.height / frozen.height)
                    val ox = (size.width - frozen.width * s) / 2; val oy = (size.height - frozen.height * s) / 2
                    fun v(o: Offset) = Offset(ox + o.x / k * s, oy + o.y / k * s)
                    taps.forEachIndexed { i, t -> drawCircle(if (i < 4) Color.Magenta else Color.Cyan, 8f, v(t)) }
                    if (taps.size >= 2) drawCircle(Color.Yellow, (v(taps[1]) - v(taps[0])).getDistance(), v(taps[0]), style = Stroke(2f))
                    var i = 4
                    while (i + 1 < taps.size) {
                        val a = v(taps[i]); val b = v(taps[i + 1])
                        drawRect(Color.Cyan, Offset(minOf(a.x, b.x), minOf(a.y, b.y)),
                            Size(kotlin.math.abs(a.x - b.x), kotlin.math.abs(a.y - b.y)), style = Stroke(3f))
                        i += 2
                    }
                }
            }
            Column(Modifier.width(380.dp).padding(16.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Calibration", fontSize = 24.sp, fontWeight = FontWeight.Bold)
                for (p in PRESETS) FilterChip(preset == p, { preset = p; maxText = p.maxValue.toString(); taps.clear() },
                    label = { Text(p.label) })
                OutlinedTextField(maxText, { maxText = it }, label = { Text("Max value on the scale (kg/cm²)") })
                Text(if (taps.size < steps.size) "Step ${taps.size + 1}/${steps.size}: ${steps[taps.size]}" else "All points tapped.",
                    fontWeight = FontWeight.Bold, color = Color(0xFF8AB4F8))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { if (taps.isNotEmpty()) taps.removeAt(taps.size - 1) }) { Text("Undo") }
                    OutlinedButton(onClick = { taps.clear() }) { Text("Restart") }
                }
                Button(enabled = taps.size == steps.size, onClick = {
                    build()?.let { cal ->
                        val a = StageA.read(full, cal)
                        val lamp = LampReader.read(full, cal).first
                        result = "Test reading: ${a.value ?: "unreadable"} (confidence ${a.confidence}), lamp $lamp.\n" +
                            "Check it matches the gauge before saving."
                    }
                }) { Text("Test reading") }
                result?.let { Text(it) }
                Button(enabled = taps.size == steps.size, onClick = {
                    build()?.let { cal ->
                        prefs.calibration = cal
                        O2App.instance.cloud.saveCalibration(prefs.deviceId, cal)
                        MonitorService.start(ctx, restart = true)
                        onDone()
                    }
                }) { Text("Save calibration") }
                OutlinedButton(onClick = onDone) { Text("Cancel") }
            }
        }
    }
}
