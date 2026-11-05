package org.o2monitor

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ContentResolver
import android.media.AudioAttributes
import android.net.Uri
import org.o2monitor.cloud.Cloud
import org.o2monitor.cloud.FirestoreCloud
import org.o2monitor.cloud.NoopCloud

class O2App : Application() {
    lateinit var prefs: Prefs; private set
    lateinit var cloud: Cloud; private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = Prefs(this)
        cloud = if (BuildConfig.HAS_FIREBASE) FirestoreCloud(this) else NoopCloud
        createChannels()
    }

    private fun createChannels() {
        val nm = getSystemService(NotificationManager::class.java)
        val alarmSound = Uri.parse("${ContentResolver.SCHEME_ANDROID_RESOURCE}://$packageName/${R.raw.o2_alarm}")
        val alarm = NotificationChannel(CH_ALARM, "Oxygen alarms", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "LOW / CRITICAL pressure, monitoring lost, tablet offline"
            setSound(alarmSound, AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 800, 300, 800, 300, 800)
            setBypassDnd(true)
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
        }
        val status = NotificationChannel(CH_MONITOR, "Monitoring status", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Shown while the tablet is monitoring the gauge"
        }
        nm.createNotificationChannels(listOf(alarm, status))
    }

    companion object {
        const val CH_ALARM = "o2_alarm_v1"
        const val CH_MONITOR = "o2_monitor"
        lateinit var instance: O2App; private set
    }
}
