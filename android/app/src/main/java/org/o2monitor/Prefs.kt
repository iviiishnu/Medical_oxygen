package org.o2monitor

import android.content.Context
import androidx.core.content.edit
import org.o2monitor.core.MonitorConfig
import org.o2monitor.vision.Calibration
import org.o2monitor.vision.FakeGaugeReader

/** Small persistent settings store (SharedPreferences). */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("o2monitor", Context.MODE_PRIVATE)

    enum class Mode { UNSET, MONITOR, STAFF }
    enum class ReaderKind { CAMERA, FAKE }

    var mode: Mode
        get() = runCatching { Mode.valueOf(sp.getString("mode", "UNSET")!!) }.getOrDefault(Mode.UNSET)
        set(v) = sp.edit { putString("mode", v.name) }

    var deviceId: String
        get() = sp.getString("device_id", "tab-main-o2-01")!!
        set(v) = sp.edit { putString("device_id", v.trim()) }

    var readerKind: ReaderKind
        get() = runCatching { ReaderKind.valueOf(sp.getString("reader", "CAMERA")!!) }.getOrDefault(ReaderKind.CAMERA)
        set(v) = sp.edit { putString("reader", v.name) }

    var fakeScenario: FakeGaugeReader.Scenario
        get() = runCatching { FakeGaugeReader.Scenario.valueOf(sp.getString("fake_scenario", "STEADY")!!) }
            .getOrDefault(FakeGaugeReader.Scenario.STEADY)
        set(v) = sp.edit { putString("fake_scenario", v.name) }

    var frameIntervalMs: Long
        get() = sp.getLong("frame_interval_ms", 1000L).coerceIn(500L, 2000L)
        set(v) = sp.edit { putLong("frame_interval_ms", v.coerceIn(500L, 2000L)) }

    var calibration: Calibration?
        get() = sp.getString("calibration", null)?.let { runCatching { Calibration.fromJson(it) }.getOrNull() }
        set(v) = sp.edit { putString("calibration", v?.toJson()) }

    /** Last config received from Firestore (survives reboots without internet). */
    var config: MonitorConfig
        get() = sp.getString("config", null)?.let { runCatching { MonitorConfig.fromJson(it) }.getOrNull() } ?: MonitorConfig()
        set(v) = sp.edit { putString("config", v.validate().toJson()) }

    var useModel: Boolean
        get() = sp.getBoolean("use_model", true)
        set(v) = sp.edit { putBoolean("use_model", v) }

    /** True while Monitor mode should be running (restarted by the home-screen activity after reboot). */
    var monitoringEnabled: Boolean
        get() = sp.getBoolean("monitoring_enabled", false)
        set(v) = sp.edit { putBoolean("monitoring_enabled", v) }
}
