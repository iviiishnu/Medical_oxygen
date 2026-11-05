package org.o2monitor.monitor

import android.graphics.Bitmap
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.o2monitor.vision.FrameResult

/** In-process bridge between MonitorService (producer) and the UI (consumer). */
object MonitorBus {
    data class Snapshot(
        val state: MonitorLogic.State = MonitorLogic.State(),
        val lastFrame: FrameResult? = null,
        val readerName: String = "",
        val running: Boolean = false,
        val cameraError: String? = null,
        val configPending: Boolean = false,
    )

    private val _snap = MutableStateFlow(Snapshot())
    val snapshot: StateFlow<Snapshot> = _snap

    /** Latest upright camera frame (for the monitor preview and the calibration screen). */
    private val _preview = MutableStateFlow<Bitmap?>(null)
    val preview: StateFlow<Bitmap?> = _preview

    fun publish(s: Snapshot) { _snap.value = s }
    fun update(f: (Snapshot) -> Snapshot) { _snap.value = f(_snap.value) }
    /** Full-resolution frame pixels per preview pixel (calibration taps are scaled by this). */
    @Volatile var previewScale: Float = 1f; private set
    @Volatile var lastFullFrame: org.o2monitor.vision.RgbImage? = null; private set

    fun publishPreview(b: Bitmap, scale: Float, full: org.o2monitor.vision.RgbImage) {
        previewScale = scale; lastFullFrame = full; _preview.value = b
    }

    /** UI -> service commands. */
    @Volatile var silenceRequestedAtMs: Long = 0
}
