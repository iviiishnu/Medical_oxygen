package org.o2monitor.monitor

import android.annotation.SuppressLint
import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.hardware.camera2.CaptureRequest
import android.os.BatteryManager
import android.os.PowerManager
import android.util.Log
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.SurfaceOrientedMeteringPointFactory
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import org.o2monitor.BuildConfig
import org.o2monitor.O2App
import org.o2monitor.Prefs
import org.o2monitor.R
import org.o2monitor.core.MonitorConfig
import org.o2monitor.core.Reading
import org.o2monitor.ui.MainActivity
import org.o2monitor.vision.CameraGaugeReader
import org.o2monitor.vision.FakeGaugeReader
import org.o2monitor.vision.FrameConvert
import org.o2monitor.vision.FrameResult
import org.o2monitor.vision.GaugeReader
import org.o2monitor.core.LampState
import org.o2monitor.vision.RgbImage
import org.o2monitor.vision.TFLiteKeypointModel
import org.o2monitor.vision.Timestamps
import java.io.Closeable
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/**
 * Monitor mode: runs as a camera foreground service.
 * ONE worker thread does everything (frames, 1 s watchdog tick, actions) so the
 * alert engine never sees concurrent calls.
 */
class MonitorService : LifecycleService() {
    private lateinit var prefs: Prefs
    private lateinit var worker: ScheduledExecutorService
    private lateinit var alarm: LocalAlarm
    private var logic: MonitorLogic? = null
    private var reader: GaugeReader? = null
    private var camera: Camera? = null
    private var configSub: Closeable? = null
    private var pendingConfig: MonitorConfig? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val alertIds = mutableMapOf<String, String>()      // alert type -> cloud doc id
    private var lastFrameMs = 0L
    private var lastFrame: RgbImage? = null
    private var lastResult: FrameResult? = null
    private var battery: Double? = null
    private var charging = true
    private var lastBatteryMs = 0L
    private var lastNotifText = ""
    private var handledSilenceAt = 0L
    private var tickFuture: java.util.concurrent.ScheduledFuture<*>? = null

    override fun onCreate() {
        super.onCreate()
        prefs = O2App.instance.prefs
        worker = Executors.newSingleThreadScheduledExecutor { r -> Thread(r, "monitor").apply { priority = Thread.MAX_PRIORITY } }
        alarm = LocalAlarm(this)
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "o2monitor:monitor").apply { setReferenceCounted(false); acquire() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val useCamera = prefs.readerKind == Prefs.ReaderKind.CAMERA
        val type = if (useCamera) ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA else 0
        try {
            ServiceCompat.startForeground(this, NOTIF_ID, notification("Starting…"), type)
        } catch (e: Exception) {
            Log.e(TAG, "cannot start foreground service", e)
            MonitorBus.update { it.copy(running = false, cameraError = "Cannot start: ${e.message}") }
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_RESTART || logic == null) worker.execute { setup(useCamera) }
        return START_STICKY
    }

    private fun setup(useCamera: Boolean) {
        val cfg = prefs.config
        logic = MonitorLogic(cfg)
        reader?.close()
        alertIds.clear()
        val cal = prefs.calibration
        reader = when {
            !useCamera -> FakeGaugeReader(cfg, prefs.fakeScenario, prefs.deviceId)
            cal == null -> null                                   // not calibrated: readings = unusable -> LOST
            else -> CameraGaugeReader(cal.copy(deviceId = prefs.deviceId), cfg,
                if (prefs.useModel) TFLiteKeypointModel.loadOrNull(this) else null)
        }
        MonitorBus.update {
            it.copy(running = true, readerName = reader?.name ?: "NOT CALIBRATED",
                cameraError = if (useCamera && cal == null) "Not calibrated - open Calibrate" else null)
        }
        configSub?.close()
        configSub = O2App.instance.cloud.observeConfig(prefs.deviceId) { c -> worker.execute { pendingConfig = c } }
        if (useCamera) ContextCompat.getMainExecutor(this).execute { bindCamera() }
        else ContextCompat.getMainExecutor(this).execute {
            runCatching { ProcessCameraProvider.getInstance(this).get().unbindAll() }
        }
        tickFuture?.cancel(false)
        tickFuture = worker.scheduleWithFixedDelay({ safe { tick() } }, 1, 1, TimeUnit.SECONDS)
    }

    // ------------------------------------------------------------------ camera
    @SuppressLint("UnsafeOptInUsageError")
    private fun bindCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                val provider = future.get()
                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(ResolutionSelector.Builder().setResolutionStrategy(
                        ResolutionStrategy(Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)).build())
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()
                analysis.setAnalyzer(worker) { proxy ->
                    proxy.use {
                        val now = System.currentTimeMillis()
                        if (now - lastFrameMs >= prefs.frameIntervalMs) {
                            lastFrameMs = now
                            safe { onCameraFrame(FrameConvert.fromImageProxy(it), now) }
                        }
                    }
                }
                provider.unbindAll()
                camera = provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, analysis)
                lockFocusAndExposure(analysis)
            } catch (e: Exception) {
                Log.e(TAG, "camera bind failed", e)
                MonitorBus.update { it.copy(cameraError = "Camera error: ${e.message}") }
            }
        }, ContextCompat.getMainExecutor(this))
    }

    /** Let AF/AE settle on the dial for 3 s, then lock focus, exposure and white balance. */
    @OptIn(ExperimentalCamera2Interop::class)
    private fun lockFocusAndExposure(analysis: ImageAnalysis) {
        val cam = camera ?: return
        val factory = SurfaceOrientedMeteringPointFactory(1f, 1f, analysis)
        val point = factory.createPoint(0.5f, 0.5f)
        cam.cameraControl.startFocusAndMetering(
            FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE)
                .disableAutoCancel().build(),
        )
        worker.schedule({
            runCatching {
                Camera2CameraControl.from(cam.cameraControl).setCaptureRequestOptions(
                    CaptureRequestOptions.Builder()
                        .setCaptureRequestOption(CaptureRequest.CONTROL_AE_LOCK, true)
                        .setCaptureRequestOption(CaptureRequest.CONTROL_AWB_LOCK, true)
                        .build(),
                )
            }.onFailure { Log.w(TAG, "AE/AWB lock not supported: ${it.message}") }
        }, 3, TimeUnit.SECONDS)
    }

    private fun onCameraFrame(img: RgbImage, now: Long) {
        lastFrame = img
        val pv = FrameConvert.toBitmap(img, 960)
        MonitorBus.publishPreview(pv, img.width.toFloat() / pv.width, img)
        val r = reader
        val fr = r?.read(img, now) ?: unusable(now)
        process(fr, now)
    }

    private fun unusable(now: Long) = FrameResult(
        Reading(prefs.deviceId, "oxygen_main", Timestamps.iso(now), null, "kg/cm2", 0.0, LampState.UNKNOWN, false, "UNCERTAIN"),
        null, null, null, 0.0,
    )

    // ------------------------------------------------------------------ loop
    private fun tick() {
        val now = System.currentTimeMillis()
        val lg = logic ?: return
        readBattery(now)
        if (MonitorBus.silenceRequestedAtMs > handledSilenceAt) {
            handledSilenceAt = MonitorBus.silenceRequestedAtMs
            lg.silence(now)
        }
        // config updates are applied only when no alert is open (never mid-incident)
        pendingConfig?.let { c ->
            if (c != lg.engine.cfg && lg.state.openAlerts.isEmpty()) {
                prefs.config = c
                pendingConfig = null
                setupLogicOnly(c)
            } else if (c == lg.engine.cfg) pendingConfig = null
        }
        val fake = reader as? FakeGaugeReader
        if (fake != null && now - lastFrameMs >= prefs.frameIntervalMs) {
            lastFrameMs = now
            fake.scenario = prefs.fakeScenario
            process(fake.read(null, now), now)
        } else {
            handle(lg.onTick(now), now)
        }
        publish()
    }

    private fun setupLogicOnly(c: MonitorConfig) {
        logic = MonitorLogic(c)
        val cal = prefs.calibration
        if (reader is CameraGaugeReader && cal != null) {
            reader?.close()
            reader = CameraGaugeReader(cal.copy(deviceId = prefs.deviceId), c,
                if (prefs.useModel) TFLiteKeypointModel.loadOrNull(this) else null)
        }
        Log.i(TAG, "applied new config $c")
    }

    private fun process(fr: FrameResult, now: Long) {
        lastResult = fr
        val lg = logic ?: return
        handle(lg.onFrame(fr, now, battery, charging), now)
        publish()
    }

    private fun handle(actions: List<MonitorLogic.Action>, now: Long) {
        val cloud = O2App.instance.cloud
        val lg = logic ?: return
        for (a in actions) when (a) {
            is MonitorLogic.Action.OpenAlert -> {
                val snap = saveSnapshot(a.type, now)
                cloud.openAlert(prefs.deviceId, lastResult?.reading?.gaugeId ?: "oxygen_main", a.type, a.value,
                    "kg/cm2", a.reason, snap)?.let { alertIds[a.type] = it }
                AuditLog.event(this, now, "OPEN ${a.type} value=${a.value} reason=${a.reason} snapshot=$snap")
            }
            is MonitorLogic.Action.ResolveAlert -> {
                alertIds.remove(a.type)?.let { cloud.resolveAlert(it, a.value) }
                AuditLog.event(this, now, "RESOLVE ${a.type} value=${a.value}")
            }
            is MonitorLogic.Action.SaveHistory -> {
                cloud.saveHistory(prefs.deviceId, a.reading, a.engineStatus, a.smoothed)
                AuditLog.reading(this, a.reading, a.engineStatus, a.smoothed)
            }
            is MonitorLogic.Action.PushLive ->
                cloud.pushLive(prefs.deviceId, a.state, lastResult?.reading, battery, charging, BuildConfig.VERSION_NAME)
        }
        if (lg.state.localAlarm) alarm.start() else alarm.stop()
        updateNotification(lg.state)
    }

    private fun publish() {
        val lg = logic ?: return
        MonitorBus.update { it.copy(state = lg.state, lastFrame = lastResult, configPending = pendingConfig != null) }
    }

    private fun readBattery(now: Long) {
        if (now - lastBatteryMs < 30_000) return
        lastBatteryMs = now
        val i = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return
        val level = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = i.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
        battery = if (level >= 0) 100.0 * level / scale else null
        val plugged = i.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)
        charging = plugged != 0
    }

    /** JPEG of the frame at every alert (audit). Keeps the newest 300. */
    private fun saveSnapshot(type: String, now: Long): String? {
        val img = lastFrame ?: return null
        return runCatching {
            val dir = File(filesDir, "snapshots").apply { mkdirs() }
            val name = "${Timestamps.iso(now).replace(":", "-")}_$type.jpg"
            File(dir, name).outputStream().use { FrameConvert.toBitmap(img).compress(Bitmap.CompressFormat.JPEG, 85, it) }
            dir.listFiles()?.sortedBy { it.name }?.dropLast(300)?.forEach { it.delete() }
            name
        }.getOrNull()
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, O2App.CH_MONITOR)
            .setSmallIcon(R.drawable.ic_stat_alarm)
            .setContentTitle("Oxygen monitor running")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(open)
            .build()
    }

    private fun updateNotification(s: MonitorLogic.State) {
        val t = "${s.status} · ${s.value?.let { "%.2f kg/cm²".format(it) } ?: "--"}"
        if (t == lastNotifText) return
        lastNotifText = t
        getSystemService(android.app.NotificationManager::class.java).notify(NOTIF_ID, notification(t))
    }

    private inline fun safe(block: () -> Unit) {
        try { block() } catch (e: Throwable) {
            // never let one bad frame kill the monitor loop; the watchdog will raise LOST if it persists
            Log.e(TAG, "monitor loop error", e)
            AuditLog.event(this, System.currentTimeMillis(), "ERROR ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    override fun onDestroy() {
        alarm.stop()
        configSub?.close()
        worker.shutdownNow()
        reader?.close()
        wakeLock?.release()
        MonitorBus.update { it.copy(running = false) }
        super.onDestroy()
    }

    companion object {
        const val TAG = "MonitorService"
        const val NOTIF_ID = 1
        const val ACTION_RESTART = "org.o2monitor.RESTART"

        fun start(ctx: Context, restart: Boolean = false) {
            val i = Intent(ctx, MonitorService::class.java)
            if (restart) i.action = ACTION_RESTART
            ContextCompat.startForegroundService(ctx, i)
        }

        fun stop(ctx: Context) = ctx.stopService(Intent(ctx, MonitorService::class.java))
    }
}
