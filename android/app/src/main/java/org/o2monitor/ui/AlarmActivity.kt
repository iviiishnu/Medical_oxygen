package org.o2monitor.ui

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.o2monitor.O2App
import org.o2monitor.staff.AlarmNotifier

/** Full-screen alarm on staff phones (shown over the lock screen). */
class AlarmActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val id = intent.getStringExtra(EXTRA_ID)
        setContent {
            O2Theme {
                val active by AlarmNotifier.active.collectAsState()
                val a = id?.let { active[it] }
                var msg by remember { mutableStateOf<String?>(null) }
                LaunchedEffect(a) { if (a == null && id != null) { msg = "Already handled"; } }
                Column(Modifier.fillMaxSize().background(StatusColors.of(a?.type ?: "OK")).padding(32.dp),
                    verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(a?.title ?: "Oxygen alert", fontSize = 34.sp, fontWeight = FontWeight.Black, color = Color.White,
                        textAlign = TextAlign.Center)
                    Text(a?.body ?: "", fontSize = 26.sp, color = Color.White)
                    Text(a?.deviceId ?: "", color = Color.White)
                    Spacer(Modifier.height(32.dp))
                    if (a != null) Button(
                        onClick = {
                            val me = O2App.instance.cloud.currentEmail() ?: "staff"
                            O2App.instance.cloud.acknowledge(a.id, me) { r ->
                                r.onSuccess { AlarmNotifier.dismiss(this@AlarmActivity, a.id, "ACKED", me); finish() }
                                    .onFailure { msg = "Could not acknowledge: ${it.message}" }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().height(96.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black),
                    ) { Text("ACKNOWLEDGE - I AM ON IT", fontSize = 24.sp, fontWeight = FontWeight.Bold) }
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { AlarmNotifier.quiet() }) { Text("Mute this phone (alert stays open)") }
                    Button(onClick = { finish() }) { Text("Close") }
                    msg?.let { Text(it, color = Color.White) }
                }
            }
        }
    }

    companion object { const val EXTRA_ID = "alert_id" }
}
