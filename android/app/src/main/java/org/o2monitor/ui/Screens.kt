package org.o2monitor.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.o2monitor.O2App
import org.o2monitor.Prefs
import org.o2monitor.cloud.AlertView
import org.o2monitor.cloud.DeviceView
import org.o2monitor.monitor.MonitorBus
import org.o2monitor.monitor.MonitorService
import org.o2monitor.vision.FakeGaugeReader

// ============================================================== setup
@Composable
fun SetupScreen(onDone: () -> Unit) {
    val app = O2App.instance
    val prefs = app.prefs
    var deviceId by remember { mutableStateOf(prefs.deviceId) }
    var email by remember { mutableStateOf(app.cloud.currentEmail() ?: "") }
    var pass by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    var signedIn by remember { mutableStateOf(app.cloud.currentUid() != null) }
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp).verticalScroll(rememberScrollState())) {
            Text("Oxygen Pressure Monitor", fontSize = 28.sp, fontWeight = FontWeight.Bold)
            Text("A monitoring aid on top of the hospital's existing alarm panel - not a replacement for it.",
                color = Color(0xFFBDC1C6))
            Spacer(Modifier.height(16.dp))
            if (app.cloud.available) {
                Section("1. Sign in") {
                    OutlinedTextField(email, { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                    OutlinedTextField(pass, { pass = it }, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(),
                        visualTransformation = PasswordVisualTransformation())
                    Button(onClick = {
                        msg = "Signing in…"
                        app.cloud.signIn(email, pass) { r ->
                            signedIn = r.isSuccess
                            msg = r.fold({ "Signed in" }, { "Sign-in failed: ${it.message}" })
                        }
                    }) { Text(if (signedIn) "Signed in ✓ (sign in again)" else "Sign in") }
                    msg?.let { Text(it) }
                }
            } else {
                Text("LOCAL-ONLY build (no Firebase configured): the tablet reads and alarms locally, " +
                    "nothing is sent to phones.", color = StatusColors.LOW)
            }
            Section("2. Choose what this device is") {
                OutlinedTextField(deviceId, { deviceId = it }, label = { Text("Tablet id (Monitor mode)") },
                    modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = {
                        prefs.deviceId = deviceId; prefs.mode = Prefs.Mode.MONITOR; prefs.monitoringEnabled = true
                        onDone()
                    }) { Text("MONITOR (tablet at the panel)") }
                    OutlinedButton(onClick = { prefs.mode = Prefs.Mode.STAFF; onDone() }) { Text("STAFF (phone)") }
                }
            }
        }
    }
}

// ============================================================== monitor
@Composable
fun MonitorScreen(onCalibrate: () -> Unit, onSettings: () -> Unit) {
    val snap by MonitorBus.snapshot.collectAsState()
    val preview by MonitorBus.preview.collectAsState()
    val ctx = LocalContext.current
    val prefs = O2App.instance.prefs
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); now = System.currentTimeMillis() } }
    val s = snap.state
    val color = StatusColors.of(s.status)
    val flash = rememberInfiniteTransition(label = "flash").animateFloat(
        1f, 0.25f, infiniteRepeatable(tween(400), RepeatMode.Reverse), label = "a")
    val bg = if (s.localAlarm) color.copy(alpha = flash.value) else color

    Row(Modifier.fillMaxSize().background(Color.Black)) {
        Column(Modifier.weight(1f).fillMaxSize().background(bg).padding(24.dp),
            verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
            Text(statusLabel(s.status), fontSize = 40.sp, fontWeight = FontWeight.Black, color = Color.White)
            Text(s.value?.let { "%.2f".format(it) } ?: "--", fontSize = 120.sp, fontWeight = FontWeight.Bold, color = Color.White)
            Text("kg/cm²", fontSize = 28.sp, color = Color.White)
            if (s.trendFalling) Text("▼ falling ${s.fallRatePerMin?.let { "%.2f".format(it) } ?: ""} /min",
                fontSize = 26.sp, color = Color.White, fontWeight = FontWeight.Bold)
            s.lostReason?.let { Text("Reason: $it", fontSize = 20.sp, color = Color.White) }
            Spacer(Modifier.height(16.dp))
            if (s.localAlarm) Button(onClick = { MonitorBus.silenceRequestedAtMs = System.currentTimeMillis() },
                colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black)) {
                Text("SILENCE 5 MIN (alerts stay active)", fontSize = 20.sp)
            }
        }
        Column(Modifier.width(420.dp).fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState())) {
            preview?.let {
                Image(it.asImageBitmap(), "camera", Modifier.fillMaxWidth().height(240.dp), contentScale = ContentScale.Fit)
            } ?: Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
                Text(if (prefs.readerKind == Prefs.ReaderKind.FAKE) "SIMULATION (fake gauge)" else "no camera frame yet")
            }
            snap.cameraError?.let { Text(it, color = StatusColors.CRITICAL, fontWeight = FontWeight.Bold) }
            if (!snap.running) Text("MONITORING IS NOT RUNNING", color = StatusColors.CRITICAL, fontWeight = FontWeight.Bold)
            Section("Live") {
                KeyValue("Reader", snap.readerName)
                KeyValue("Last frame", ago(s.lastFrameEpochMs).let { if (s.lastFrameEpochMs == null) it else "${(now - s.lastFrameEpochMs) / 1000}s ago" })
                KeyValue("Raw reading", s.rawValue?.let { "%.2f".format(it) } ?: "--")
                KeyValue("Confidence", "%.2f".format(s.confidence))
                KeyValue("Panel lamp", s.lampState)
                KeyValue("Frame status", s.frameStatus)
                KeyValue("Processing", "%.0f ms".format(s.inferenceMs))
                snap.lastFrame?.stageA?.let { KeyValue("Stage A", "${it.value ?: "--"} (${it.confidence})") }
                snap.lastFrame?.stageB?.let { KeyValue("Stage B model", "${it.value ?: "--"} (${it.confidence})") }
                KeyValue("Open alerts", s.openAlerts.joinToString().ifEmpty { "none" })
                if (snap.configPending) KeyValue("Config", "update waiting (applies when no alert is open)")
                KeyValue("Cloud", if (O2App.instance.cloud.available) (O2App.instance.cloud.currentEmail() ?: "NOT SIGNED IN") else "local only")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onCalibrate) { Text("Calibrate") }
                OutlinedButton(onClick = onSettings) { Text("Settings") }
                OutlinedButton(onClick = {
                    if (snap.running) { prefs.monitoringEnabled = false; MonitorService.stop(ctx) }
                    else { prefs.monitoringEnabled = true; MonitorService.start(ctx, restart = true) }
                }) { Text(if (snap.running) "Stop" else "Start") }
            }
        }
    }
}

// ============================================================== staff
@Composable
fun StaffScreen(onSettings: () -> Unit) {
    val cloud = O2App.instance.cloud
    var devices by remember { mutableStateOf<List<DeviceView>>(emptyList()) }
    var alerts by remember { mutableStateOf<List<AlertView>>(emptyList()) }
    var info by remember { mutableStateOf<String?>(null) }
    var tick by remember { mutableLongStateOf(0L) }
    DisposableEffect(Unit) {
        val a = cloud.observeDevices { devices = it }
        val b = cloud.observeAlerts { alerts = it }
        onDispose { a.close(); b.close() }
    }
    LaunchedEffect(Unit) { while (true) { delay(5000); tick++ } }
    val myName = cloud.currentEmail() ?: "staff"
    Surface(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Oxygen supply", fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    OutlinedButton(onClick = onSettings) { Text("Settings") }
                }
                if (!cloud.available) Text("Local-only build: Staff mode needs Firebase.", color = StatusColors.CRITICAL)
                else if (cloud.currentUid() == null) Text("Not signed in - open Settings.", color = StatusColors.CRITICAL)
                info?.let { Text(it) }
            }
            items(devices, key = { "d" + it.id }) { d ->
                val stale = d.lastHeartbeatMs == null || System.currentTimeMillis() - d.lastHeartbeatMs > 65_000
                val status = if (!d.online || stale) "TABLET_OFFLINE" else d.status
                Card(colors = CardDefaults.cardColors(containerColor = StatusColors.of(status))) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) {
                        Text(d.name, color = Color.White, fontWeight = FontWeight.Bold)
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text(d.value?.let { "%.2f".format(it) } ?: "--", fontSize = 48.sp, color = Color.White, fontWeight = FontWeight.Bold)
                            Text(" ${d.unit}", color = Color.White)
                        }
                        Text(statusLabel(status) + if (d.trendFalling) "  ▼ falling" else "", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("updated ${ago(d.lastHeartbeatMs)}" + (d.battery?.let { " · battery %.0f%%".format(it) } ?: ""),
                            color = Color.White)
                    }
                }
            }
            item { Text("Alerts (24 h)", fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 12.dp)) }
            items(alerts, key = { "a" + it.id }) { a ->
                Card {
                    Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(10.dp).height(48.dp).background(StatusColors.of(a.type)))
                        Column(Modifier.weight(1f).padding(start = 12.dp)) {
                            Text("${statusLabel(a.type)}  ${a.value?.let { "%.2f".format(it) } ?: ""}", fontWeight = FontWeight.Bold)
                            Text("${a.deviceId} · ${fmtTime(a.createdMs)} · ${a.state}" +
                                (a.ackedByName?.let { " by $it ${fmtTime(a.ackedMs)}" } ?: ""))
                        }
                        if (a.state == "OPEN") Button(onClick = {
                            cloud.acknowledge(a.id, myName) { r -> info = r.fold({ "Acknowledged" }, { "Ack failed: ${it.message}" }) }
                        }) { Text("ACK") }
                    }
                }
            }
        }
    }
}

// ============================================================== settings
@Composable
fun SettingsScreen(onBack: () -> Unit, onResetMode: () -> Unit) {
    val ctx = LocalContext.current
    val app = O2App.instance
    val prefs = app.prefs
    var reader by remember { mutableStateOf(prefs.readerKind) }
    var scenario by remember { mutableStateOf(prefs.fakeScenario) }
    var interval by remember { mutableLongStateOf(prefs.frameIntervalMs) }
    var useModel by remember { mutableStateOf(prefs.useModel) }
    var onDuty by remember { mutableStateOf(true) }
    val restart = { if (prefs.mode == Prefs.Mode.MONITOR && prefs.monitoringEnabled) MonitorService.start(ctx, restart = true) }
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp).verticalScroll(rememberScrollState())) {
            Text("Settings", fontSize = 26.sp, fontWeight = FontWeight.Bold)
            KeyValue("Mode", prefs.mode.name)
            KeyValue("Device id", prefs.deviceId)
            KeyValue("Signed in as", app.cloud.currentEmail() ?: "-")
            val cfg = prefs.config
            KeyValue("LOW / CRITICAL", "${cfg.lowThreshold} / ${cfg.criticalThreshold} kg/cm² (set by admin)")
            if (prefs.mode == Prefs.Mode.MONITOR) {
                Section("Gauge reader") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (k in Prefs.ReaderKind.entries) FilterChip(reader == k, {
                            reader = k; prefs.readerKind = k; restart()
                        }, label = { Text(if (k == Prefs.ReaderKind.CAMERA) "Camera" else "Simulation") })
                    }
                    if (reader == Prefs.ReaderKind.FAKE) {
                        Text("Simulation scenario (for demos and tests):")
                        Column {
                            for (sc in FakeGaugeReader.Scenario.entries) FilterChip(scenario == sc, {
                                scenario = sc; prefs.fakeScenario = sc
                            }, label = { Text(sc.name) })
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(useModel, { useModel = it; prefs.useModel = it; restart() })
                        Text("  Use keypoint model (Stage B) together with Stage A")
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (ms in listOf(1000L, 1500L, 2000L)) FilterChip(interval == ms, {
                            interval = ms; prefs.frameIntervalMs = ms
                        }, label = { Text("1 frame / ${ms / 1000.0}s") })
                    }
                }
            } else {
                Section("Notifications") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(onDuty, { onDuty = it; app.cloud.setOnDuty(it) })
                        Text("  On duty (receive alarm pushes)")
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onBack) { Text("Back") }
                OutlinedButton(onClick = {
                    MonitorService.stop(ctx); prefs.monitoringEnabled = false; prefs.mode = Prefs.Mode.UNSET; onResetMode()
                }) { Text("Change mode / sign in") }
                OutlinedButton(onClick = { app.cloud.signOut() }) { Text("Sign out") }
            }
        }
    }
}
