package org.o2monitor.staff

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.o2monitor.O2App
import org.o2monitor.R
import org.o2monitor.monitor.LocalAlarm
import org.o2monitor.ui.AlarmActivity

/** Staff phones: full-screen alarm notification + looping sound until acknowledged. */
object AlarmNotifier {
    data class Alert(val id: String, val type: String, val title: String, val body: String,
                     val deviceId: String, val level: Int)

    private val _active = MutableStateFlow<Map<String, Alert>>(emptyMap())
    val active: StateFlow<Map<String, Alert>> = _active
    private var sound: LocalAlarm? = null

    private fun nid(id: String) = 1000 + (id.hashCode() and 0x7fff)

    @Synchronized
    fun show(ctx: Context, a: Alert) {
        _active.value = _active.value + (a.id to a)
        val full = PendingIntent.getActivity(ctx, nid(a.id),
            Intent(ctx, AlarmActivity::class.java).putExtra(AlarmActivity.EXTRA_ID, a.id)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(ctx, O2App.CH_ALARM)
            .setSmallIcon(R.drawable.ic_stat_alarm)
            .setContentTitle(a.title + if (a.level > 0) "  (escalated)" else "")
            .setContentText(a.body)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setFullScreenIntent(full, true)
            .setContentIntent(full)
            .setOngoing(true)
            .setAutoCancel(false)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(nid(a.id), n)
        if (sound == null) sound = LocalAlarm(ctx.applicationContext)
        sound?.start()
    }

    @Synchronized
    fun dismiss(ctx: Context, id: String, state: String = "ACKED", by: String? = null) {
        _active.value = _active.value - id
        ctx.getSystemService(NotificationManager::class.java).cancel(nid(id))
        if (_active.value.isEmpty()) sound?.stop()
        lastDismissed.value = "${state.lowercase()}${by?.let { " by $it" } ?: ""}"
    }

    /** Stop the sound locally (e.g. user opened the alarm screen) without acknowledging. */
    fun quiet() { sound?.stop() }

    val lastDismissed = MutableStateFlow<String?>(null)
}
