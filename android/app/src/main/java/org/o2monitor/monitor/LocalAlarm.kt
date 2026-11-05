package org.o2monitor.monitor

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.util.Log
import org.o2monitor.R

/**
 * The FIRST alarm layer: loud sound on the tablet itself, no network needed.
 * Uses the bundled res/raw/o2_alarm.wav on the ALARM stream at full volume;
 * falls back to a ToneGenerator if the media player cannot start.
 */
class LocalAlarm(private val ctx: Context) {
    private var player: MediaPlayer? = null
    private var tone: ToneGenerator? = null
    @Volatile var ringing = false; private set

    @Synchronized
    fun start() {
        if (ringing) return
        ringing = true
        val am = ctx.getSystemService(AudioManager::class.java)
        runCatching { am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0) }
        try {
            player = MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                val afd = ctx.resources.openRawResourceFd(R.raw.o2_alarm)
                setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
                afd.close()
                isLooping = true
                prepare()
                start()
            }
        } catch (e: Exception) {
            Log.e(TAG, "media player failed, using tone generator", e)
            player = null
            tone = ToneGenerator(AudioManager.STREAM_ALARM, ToneGenerator.MAX_VOLUME).also {
                it.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK)
            }
        }
    }

    @Synchronized
    fun stop() {
        if (!ringing) return
        ringing = false
        runCatching { player?.stop() }
        runCatching { player?.release() }
        player = null
        runCatching { tone?.stopTone(); tone?.release() }
        tone = null
    }

    companion object { const val TAG = "LocalAlarm" }
}
