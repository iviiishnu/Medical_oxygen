package org.o2monitor.monitor

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import org.o2monitor.O2App
import org.o2monitor.R
import org.o2monitor.ui.MainActivity

/**
 * After a reboot / app update. Android 14+ does not allow a camera foreground service to start
 * from BOOT_COMPLETED, so monitoring is resumed by the activity:
 *  - in Monitor mode the app is registered as the HOME app, so it opens by itself after boot;
 *  - as a fallback we post a full-screen "tap to resume monitoring" alarm notification.
 * Meanwhile the missing heartbeat makes the server raise TABLET_OFFLINE to staff phones.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val prefs = O2App.instance.prefs
        if (!prefs.monitoringEnabled) return
        val open = PendingIntent.getActivity(
            ctx, 1, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val n = NotificationCompat.Builder(ctx, O2App.CH_ALARM)
            .setSmallIcon(R.drawable.ic_stat_alarm)
            .setContentTitle("Oxygen monitor stopped (restart)")
            .setContentText("Tap to resume monitoring the oxygen panel")
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setFullScreenIntent(open, true)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(NOTIF_RESUME, n)
    }

    companion object { const val NOTIF_RESUME = 3 }
}
