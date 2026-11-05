package org.o2monitor.cloud

import android.content.Context
import android.util.Log
import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.firebase.firestore.SetOptions
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.o2monitor.core.MonitorConfig
import org.o2monitor.core.Reading
import org.o2monitor.monitor.MonitorLogic
import org.o2monitor.vision.Calibration
import java.io.Closeable
import java.util.Date

/** Firestore implementation. Data model: firebase/README (devices, readings, alerts, staff). */
class FirestoreCloud(ctx: Context) : Cloud {
    private val db = FirebaseFirestore.getInstance()
    private val auth = FirebaseAuth.getInstance()
    override val available = true

    override fun currentUid(): String? = auth.currentUser?.uid
    override fun currentEmail(): String? = auth.currentUser?.email

    override fun signIn(email: String, password: String, done: (Result<String>) -> Unit) {
        auth.signInWithEmailAndPassword(email.trim(), password)
            .addOnSuccessListener { r ->
                // pick up custom claims (role / device_id) immediately
                r.user?.getIdToken(true)?.addOnCompleteListener { done(Result.success(r.user!!.uid)) }
                    ?: done(Result.success(r.user!!.uid))
            }
            .addOnFailureListener { done(Result.failure(it)) }
    }

    override fun signOut() = auth.signOut()

    private fun readingMap(r: Reading): Map<String, Any?> = mapOf(
        "device_id" to r.deviceId, "gauge_id" to r.gaugeId, "ts" to r.ts, "value" to r.value,
        "unit" to r.unit, "confidence" to r.confidence, "lamp_state" to r.lampState,
        "method_agree" to r.methodAgree, "status" to r.status,
    )

    private fun log(op: String) = com.google.android.gms.tasks.OnFailureListener { e -> Log.w(TAG, "$op failed: ${e.message}") }

    override fun pushLive(deviceId: String, s: MonitorLogic.State, r: Reading?, battery: Double?, charging: Boolean, appVersion: String) {
        if (auth.currentUser == null) return
        val m = mutableMapOf<String, Any?>(
            "status" to s.status, "alarm" to s.alarm, "trend_falling" to s.trendFalling,
            "lost_reason" to s.lostReason, "last_heartbeat" to FieldValue.serverTimestamp(),
            "last_seen_local" to Timestamp(Date()), "battery" to battery, "charging" to charging,
            "app_version" to appVersion,
        )
        if (r != null) m["last_reading"] = readingMap(r) + mapOf("smoothed" to s.value, "engine_status" to s.status)
        db.collection("devices").document(deviceId).set(m, SetOptions.merge()).addOnFailureListener(log("pushLive"))
    }

    override fun saveHistory(deviceId: String, r: Reading, engineStatus: String, smoothed: Double?) {
        if (auth.currentUser == null) return
        val m = readingMap(r) + mapOf(
            "frame_status" to r.status, "status" to engineStatus, "smoothed" to smoothed,
            "server_ts" to FieldValue.serverTimestamp(),
            "expire_at" to Timestamp(Date(System.currentTimeMillis() + 90L * 24 * 3600 * 1000)),
        )
        db.collection("devices").document(deviceId).collection("readings").add(m).addOnFailureListener(log("history"))
    }

    override fun openAlert(deviceId: String, gaugeId: String, type: String, value: Double?, unit: String,
                           reason: String?, snapshot: String?): String? {
        if (auth.currentUser == null) return null
        val ref = db.collection("alerts").document()                     // id generated locally (offline ok)
        ref.set(mapOf(
            "type" to type, "state" to "OPEN", "device_id" to deviceId, "gauge_id" to gaugeId,
            "value" to value, "unit" to unit, "reason" to reason, "snapshot" to snapshot,
            "source" to "tablet", "created_at" to FieldValue.serverTimestamp(),
            "client_ts" to Timestamp(Date()), "escalation_level" to 0,
        )).addOnFailureListener(log("openAlert"))
        return ref.id
    }

    override fun resolveAlert(alertId: String, value: Double?) {
        if (auth.currentUser == null) return
        db.collection("alerts").document(alertId).update(mapOf(
            "state" to "RESOLVED", "resolved_at" to FieldValue.serverTimestamp(), "resolve_value" to value,
        )).addOnFailureListener(log("resolveAlert"))
    }

    override fun saveCalibration(deviceId: String, cal: Calibration) {
        if (auth.currentUser == null) return
        db.collection("devices").document(deviceId)
            .set(mapOf("calibration" to cal.toJson()), SetOptions.merge()).addOnFailureListener(log("calibration"))
    }

    override fun observeConfig(deviceId: String, onChange: (MonitorConfig) -> Unit): Closeable {
        val reg = db.collection("devices").document(deviceId).addSnapshotListener { snap, err ->
            if (err != null || snap == null) return@addSnapshotListener
            @Suppress("UNCHECKED_CAST")
            val cfg = snap.get("config") as? Map<String, Any?> ?: return@addSnapshotListener
            runCatching { MonitorConfig.fromJson(mapToJson(cfg).toString()) }
                .onSuccess(onChange)
                .onFailure { Log.w(TAG, "bad config in Firestore: ${it.message}") }
        }
        return Closeable { reg.remove() }
    }

    override fun observeDevices(cb: (List<DeviceView>) -> Unit): Closeable {
        val reg = db.collection("devices").addSnapshotListener { snap, err ->
            if (err != null || snap == null) return@addSnapshotListener
            cb(snap.documents.map { d ->
                @Suppress("UNCHECKED_CAST")
                val lr = d.get("last_reading") as? Map<String, Any?>
                DeviceView(
                    id = d.id, name = d.getString("name") ?: d.id,
                    value = (lr?.get("smoothed") as? Number)?.toDouble() ?: (lr?.get("value") as? Number)?.toDouble(),
                    unit = lr?.get("unit") as? String ?: "kg/cm2",
                    status = d.getString("status") ?: "UNKNOWN", alarm = d.getString("alarm") ?: "OK",
                    trendFalling = d.getBoolean("trend_falling") ?: false,
                    lastHeartbeatMs = d.getTimestamp("last_heartbeat")?.toDate()?.time,
                    online = d.getBoolean("online") != false,
                    battery = d.getDouble("battery"),
                )
            }.sortedBy { it.name })
        }
        return Closeable { reg.remove() }
    }

    override fun observeAlerts(cb: (List<AlertView>) -> Unit): Closeable {
        val since = Timestamp(Date(System.currentTimeMillis() - 24L * 3600 * 1000))
        val reg = db.collection("alerts").whereGreaterThan("created_at", since)
            .orderBy("created_at", Query.Direction.DESCENDING).limit(200)
            .addSnapshotListener { snap, err ->
                if (err != null || snap == null) return@addSnapshotListener
                cb(snap.documents.map { d ->
                    AlertView(
                        id = d.id, type = d.getString("type") ?: "?", state = d.getString("state") ?: "OPEN",
                        deviceId = d.getString("device_id") ?: "", value = d.getDouble("value"),
                        unit = d.getString("unit") ?: "kg/cm2",
                        createdMs = d.getTimestamp("created_at")?.toDate()?.time,
                        ackedByName = d.getString("acked_by_name"),
                        ackedMs = d.getTimestamp("acked_at")?.toDate()?.time,
                        resolvedMs = d.getTimestamp("resolved_at")?.toDate()?.time,
                    )
                })
            }
        return Closeable { reg.remove() }
    }

    override fun acknowledge(alertId: String, name: String, done: (Result<Unit>) -> Unit) {
        val uid = auth.currentUser?.uid ?: return done(Result.failure(IllegalStateException("not signed in")))
        db.collection("alerts").document(alertId).update(mapOf(
            "state" to "ACKED", "acked_by" to uid, "acked_by_name" to name, "acked_at" to FieldValue.serverTimestamp(),
        )).addOnSuccessListener { done(Result.success(Unit)) }.addOnFailureListener { done(Result.failure(it)) }
    }

    override fun registerToken(token: String) {
        val uid = auth.currentUser?.uid ?: return
        db.collection("staff").document(uid).update(mapOf("fcm_tokens" to FieldValue.arrayUnion(token)))
            .addOnFailureListener(log("registerToken"))
    }

    override fun setOnDuty(onDuty: Boolean) {
        val uid = auth.currentUser?.uid ?: return
        db.collection("staff").document(uid).update(mapOf("on_duty" to onDuty)).addOnFailureListener(log("onDuty"))
    }

    private fun mapToJson(m: Map<String, Any?>): JsonObject = buildJsonObject {
        for ((k, v) in m) when (v) {
            is Number -> put(k, JsonPrimitive(v))
            is Boolean -> put(k, JsonPrimitive(v))
            is String -> put(k, JsonPrimitive(v))
            null -> put(k, kotlinx.serialization.json.JsonNull)
            else -> {}
        }
    }

    companion object {
        const val TAG = "FirestoreCloud"
    }
}
