package info.dvkr.screenstream

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.Bundle
import info.dvkr.screenstream.rtsp.RtspClockProbe
import info.dvkr.screenstream.rtsp.RtspTransportFacade
import org.koin.core.context.GlobalContext

/** Shell-protected clock and sync-frame control plane for local ADB diagnostics. */
public class ClockProbeProvider : ContentProvider() {
    override fun onCreate(): Boolean = true

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor {
        require(uri.lastPathSegment == "snapshot") { "clock_snapshot_path_required" }
        val clock = RtspClockProbe.snapshot()
        return MatrixCursor(COLUMNS).apply {
            addRow(
                arrayOf(
                    clock.sessionEpochId,
                    clock.anchorElapsedRealtimeNs,
                    clock.anchorWallClockMs,
                    clock.latestVideoPtsUs,
                    clock.latestAudioPtsUs,
                    clock.lastMediaEmitElapsedRealtimeNs
                )
            )
        }
    }

    override fun getType(uri: Uri): String = "vnd.android.cursor.item/vnd.cn.zhixingzhixue.clock"
    override fun call(method: String, arg: String?, extras: Bundle?): Bundle? {
        context?.enforceCallingPermission("android.permission.DUMP", "DUMP permission required for RTSP diagnostics")
        return when (method) {
            METHOD_REQUEST_SYNC_FRAME -> {
                GlobalContext.get().get<RtspTransportFacade>().requestSyncFrame()
                Bundle().apply { putBoolean("requested", true) }
            }
            else -> super.call(method, arg, extras)
        }
    }
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int = 0

    private companion object {
        private const val METHOD_REQUEST_SYNC_FRAME: String = "request_sync_frame"
        private val COLUMNS: Array<String> = arrayOf(
            "session_epoch_id",
            "anchor_elapsed_realtime_ns",
            "anchor_wall_clock_ms",
            "latest_video_pts_us",
            "latest_audio_pts_us",
            "last_media_emit_elapsed_realtime_ns"
        )
    }
}
