package org.o2monitor.monitor

import android.content.Context
import org.o2monitor.core.Reading
import org.o2monitor.vision.Timestamps
import java.io.File

/**
 * Local audit trail on the tablet (works with no internet):
 *   files/audit/readings-YYYY-MM-DD.csv  - one row per minute + every status change
 *   files/audit/events-YYYY-MM-DD.log    - alert open/resolve, errors
 * Files older than 120 days are deleted.
 */
object AuditLog {
    private fun dir(ctx: Context) = File(ctx.filesDir, "audit").apply { mkdirs() }
    private fun day(iso: String) = iso.take(10)

    @Synchronized
    fun reading(ctx: Context, r: Reading, engineStatus: String, smoothed: Double?) {
        val f = File(dir(ctx), "readings-${day(r.ts)}.csv")
        val header = !f.exists()
        f.appendText(buildString {
            if (header) append("ts,value,smoothed,confidence,lamp_state,method_agree,frame_status,status\n")
            append("${r.ts},${r.value ?: ""},${smoothed ?: ""},${r.confidence},${r.lampState},${r.methodAgree},${r.status},$engineStatus\n")
        })
        prune(ctx)
    }

    @Synchronized
    fun event(ctx: Context, epochMs: Long, text: String) {
        val ts = Timestamps.iso(epochMs)
        File(dir(ctx), "events-${day(ts)}.log").appendText("$ts $text\n")
    }

    private var lastPrune = 0L
    private fun prune(ctx: Context) {
        val now = System.currentTimeMillis()
        if (now - lastPrune < 24 * 3600_000L) return
        lastPrune = now
        dir(ctx).listFiles()?.filter { now - it.lastModified() > 120L * 24 * 3600_000 }?.forEach { it.delete() }
    }
}
