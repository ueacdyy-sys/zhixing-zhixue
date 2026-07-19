package info.dvkr.screenstream

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import info.dvkr.screenstream.rtsp.RtspClockProbe
import org.json.JSONObject
import java.io.File

/** ADB-only timing probe; it deliberately returns no media, OCR, or user data. */
public class ClockSnapshotReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_CLOCK_SNAPSHOT) return
        val clock = RtspClockProbe.snapshot()
        val payload = JSONObject()
            .put("session_epoch_id", clock.sessionEpochId)
            .put("anchor_elapsed_realtime_ns", clock.anchorElapsedRealtimeNs)
            .put("anchor_wall_clock_ms", clock.anchorWallClockMs)
            .put("latest_video_pts_us", clock.latestVideoPtsUs)
            .put("latest_audio_pts_us", clock.latestAudioPtsUs)
            .put("last_media_emit_elapsed_realtime_ns", clock.lastMediaEmitElapsedRealtimeNs)
            .toString()
        val finalFile = File(context.filesDir, "rtsp_clock_snapshot.json")
        val partialFile = File(context.filesDir, "rtsp_clock_snapshot.json.partial")
        partialFile.writeText(payload, Charsets.UTF_8)
        if (!partialFile.renameTo(finalFile)) {
            partialFile.delete()
            throw IllegalStateException("clock_snapshot_atomic_replace_failed")
        }
        resultData = payload
    }

    public companion object {
        public const val ACTION_CLOCK_SNAPSHOT: String = "cn.zhixingzhixue.mobile.action.CLOCK_SNAPSHOT"
    }
}
