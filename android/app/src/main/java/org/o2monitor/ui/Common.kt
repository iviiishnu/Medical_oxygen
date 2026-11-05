package org.o2monitor.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object StatusColors {
    val OK = Color(0xFF1E8E3E)
    val LOW = Color(0xFFE37400)
    val CRITICAL = Color(0xFFC5221F)
    val UNCERTAIN = Color(0xFF8E6C00)
    val LOST = Color(0xFF7B1FA2)
    val UNKNOWN = Color(0xFF5F6368)
    fun of(status: String) = when (status) {
        "OK" -> OK; "LOW" -> LOW; "CRITICAL" -> CRITICAL; "UNCERTAIN" -> UNCERTAIN
        "MONITORING_LOST", "TABLET_OFFLINE" -> LOST; else -> UNKNOWN
    }
}

fun statusLabel(s: String) = when (s) {
    "OK" -> "NORMAL"
    "LOW" -> "LOW PRESSURE"
    "CRITICAL" -> "CRITICAL - VERY LOW"
    "UNCERTAIN" -> "READING UNCERTAIN"
    "MONITORING_LOST" -> "MONITORING LOST"
    "TABLET_OFFLINE" -> "TABLET OFFLINE"
    "TREND_FALLING" -> "PRESSURE FALLING"
    else -> s
}

fun fmtTime(ms: Long?): String =
    if (ms == null) "--" else SimpleDateFormat("HH:mm:ss", Locale.US).format(Date(ms))

fun ago(ms: Long?): String {
    if (ms == null) return "never"
    val s = (System.currentTimeMillis() - ms) / 1000
    return when { s < 0 -> "now"; s < 90 -> "${s}s ago"; s < 5400 -> "${s / 60} min ago"; else -> "${s / 3600} h ago" }
}

@Composable
fun O2Theme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFF8AB4F8)), content = content)
}

@Composable
fun KeyValue(k: String, v: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(k, color = Color(0xFFBDC1C6)); Text(v)
    }
}

@Composable
fun Section(title: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium, color = Color(0xFF8AB4F8))
        content()
    }
}
