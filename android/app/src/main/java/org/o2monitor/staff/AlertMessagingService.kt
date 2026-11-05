package org.o2monitor.staff

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import org.o2monitor.O2App

/**
 * Receives the data-only, high-priority FCM messages sent by the Cloud Functions.
 * Runs even when the app is closed (data messages + priority high).
 */
class AlertMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(msg: RemoteMessage) {
        val d = msg.data
        when (d["kind"]) {
            "ALERT" -> AlarmNotifier.show(this, AlarmNotifier.Alert(
                id = d["alert_id"] ?: return,
                type = d["type"] ?: "ALERT",
                title = d["title"] ?: "Oxygen alert",
                body = d["body"] ?: "",
                deviceId = d["device_id"] ?: "",
                level = d["level"]?.toIntOrNull() ?: 0,
            ))
            "ALERT_UPDATE" -> AlarmNotifier.dismiss(this, d["alert_id"] ?: return,
                d["state"] ?: "ACKED", d["acked_by_name"])
        }
    }

    override fun onNewToken(token: String) {
        O2App.instance.cloud.registerToken(token)
    }
}
