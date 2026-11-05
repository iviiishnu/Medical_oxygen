package org.o2monitor.ui

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessaging
import org.o2monitor.BuildConfig
import org.o2monitor.O2App
import org.o2monitor.Prefs
import org.o2monitor.monitor.MonitorService

class MainActivity : ComponentActivity() {
    private val prefs get() = O2App.instance.prefs

    private val permLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (prefs.mode == Prefs.Mode.MONITOR && prefs.monitoringEnabled) MonitorService.start(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestPermissions()
        applyModeSideEffects()
        setContent {
            O2Theme {
                var screen by remember { mutableStateOf(if (prefs.mode == Prefs.Mode.UNSET) Screen.SETUP else Screen.HOME) }
                val go: (Screen) -> Unit = { screen = it; applyModeSideEffects() }
                when (screen) {
                    Screen.SETUP -> SetupScreen(onDone = { go(Screen.HOME) })
                    Screen.HOME -> if (prefs.mode == Prefs.Mode.MONITOR)
                        MonitorScreen(onCalibrate = { go(Screen.CALIBRATE) }, onSettings = { go(Screen.SETTINGS) })
                    else StaffScreen(onSettings = { go(Screen.SETTINGS) })
                    Screen.CALIBRATE -> CalibrationScreen(onDone = { go(Screen.HOME) })
                    Screen.SETTINGS -> SettingsScreen(onBack = { go(Screen.HOME) }, onResetMode = { go(Screen.SETUP) })
                }
            }
        }
    }

    enum class Screen { SETUP, HOME, CALIBRATE, SETTINGS }

    private fun requestPermissions() {
        val want = mutableListOf(Manifest.permission.CAMERA)
        if (Build.VERSION.SDK_INT >= 33) want += Manifest.permission.POST_NOTIFICATIONS
        val missing = want.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) permLauncher.launch(missing.toTypedArray())
    }

    /** Monitor mode: keep screen on, be the home app (auto-resume after reboot), start the service.
     *  Staff mode: register this phone for pushes. */
    private fun applyModeSideEffects() {
        val home = ComponentName(this, "org.o2monitor.ui.MonitorHomeAlias")
        val monitor = prefs.mode == Prefs.Mode.MONITOR
        packageManager.setComponentEnabledSetting(home,
            if (monitor) PackageManager.COMPONENT_ENABLED_STATE_ENABLED else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP)
        if (monitor) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            if (prefs.monitoringEnabled) MonitorService.start(this)
            askIgnoreBatteryOptimisation()
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            if (prefs.mode == Prefs.Mode.STAFF && BuildConfig.HAS_FIREBASE) {
                FirebaseMessaging.getInstance().token.addOnSuccessListener { O2App.instance.cloud.registerToken(it) }
            }
        }
    }

    private var askedBattery = false

    private fun askIgnoreBatteryOptimisation() {
        if (askedBattery) return
        askedBattery = true
        val pm = getSystemService(PowerManager::class.java)
        if (!pm.isIgnoringBatteryOptimizations(packageName)) {
            runCatching {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
            }
        }
    }
}
