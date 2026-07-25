package info.dvkr.screenstream.rtsp

import android.os.Handler
import android.os.Looper
import android.content.Intent
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import info.dvkr.screenstream.rtsp.internal.MasterClock
import info.dvkr.screenstream.rtsp.internal.RtspEvent
import info.dvkr.screenstream.rtsp.internal.RtspStreamingService

/** Stable, business-safe read model for the ScreenStream RTSP transport. */
public enum class RtspTransportStatus {
    IDLE,
    STARTING,
    WAITING_FOR_USER_PERMISSION,
    STREAMING,
    STREAMING_NO_CONSUMER,
    ERROR
}

public data class RtspTransportSnapshot(
    val status: RtspTransportStatus,
    val activeConsumerCount: Int,
    val endpoint: String?,
    val deviceAudioAvailable: Boolean,
    val failureCode: String?,
    /** Present only while the user-authorized MediaProjection dialog is pending. */
    val startAttemptId: String? = null,
    val timing: RtspTransportTimingSnapshot? = null
)

/** Read-only clock facts for one user-authorized RTSP capture session. */
public data class RtspTransportTimingSnapshot(
    val sessionEpochId: Long,
    val anchorElapsedRealtimeNs: Long?,
    val anchorWallClockMs: Long?,
    val latestVideoPtsUs: Long?,
    val latestAudioPtsUs: Long?,
    val lastMediaEmitElapsedRealtimeNs: Long?
)

/** Immutable timing facts exposed only through the app's shell-protected probe. */
public data class RtspClockFacts(
    val sessionEpochId: Long,
    val anchorElapsedRealtimeNs: Long?,
    val anchorWallClockMs: Long?,
    val latestVideoPtsUs: Long?,
    val latestAudioPtsUs: Long?,
    val lastMediaEmitElapsedRealtimeNs: Long?
)

/**
 * Read-only bridge for controlled performance measurement. It cannot start,
 * stop, configure, or capture media; the installable app gates access with
 * android.permission.DUMP so only ADB/system diagnostics can query it.
 */
public object RtspClockProbe {
    public fun snapshot(): RtspClockFacts {
        val clock = MasterClock.snapshot()
        return RtspClockFacts(
            sessionEpochId = clock.sessionEpochId,
            anchorElapsedRealtimeNs = clock.anchorElapsedRealtimeNs,
            anchorWallClockMs = clock.anchorWallClockMs,
            latestVideoPtsUs = clock.latestVideoPtsUs,
            latestAudioPtsUs = clock.latestAudioPtsUs,
            lastMediaEmitElapsedRealtimeNs = clock.lastMediaEmitElapsedRealtimeNs
        )
    }
}

/**
 * Bridge between the V5 media-session screen and the existing RTSP module.
 * Capture can only be initiated from a foreground UI action and still requires
 * the system MediaProjection dialog; the facade never starts capture itself.
 */
public class RtspTransportFacade(private val module: RtspStreamingModule) {
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    public val state: StateFlow<RtspTransportSnapshot> = module.rtspStateFlow
        .map { source ->
            val consumerCount = source.serverClientStats.count { it.lastSentAtMs > 0L }
            val status = when {
                // A new capture request is authoritative while its
                // MediaProjection consent is outstanding.  A recoverable
                // error from an earlier attempt may still be retained by the
                // RTSP service, but it must never hide the new attempt: doing
                // so prevents the Compose permission launcher from receiving
                // startAttemptId and leaves the request suspended forever.
                source.waitingCastPermission -> RtspTransportStatus.WAITING_FOR_USER_PERMISSION
                source.error != null -> RtspTransportStatus.ERROR
                source.isStreaming && consumerCount == 0 -> RtspTransportStatus.STREAMING_NO_CONSUMER
                source.isStreaming -> RtspTransportStatus.STREAMING
                source.isBusy -> RtspTransportStatus.STARTING
                else -> RtspTransportStatus.IDLE
            }
            RtspTransportSnapshot(
                status = status,
                activeConsumerCount = consumerCount,
                endpoint = source.serverBindings.firstOrNull()?.fullAddress,
                deviceAudioAvailable = source.selectedAudioEncoder != null,
                failureCode = source.error?.javaClass?.simpleName,
                startAttemptId = source.startAttemptId,
                timing = MasterClock.snapshot().let { clock ->
                    RtspTransportTimingSnapshot(
                        sessionEpochId = clock.sessionEpochId,
                        anchorElapsedRealtimeNs = clock.anchorElapsedRealtimeNs,
                        anchorWallClockMs = clock.anchorWallClockMs,
                        latestVideoPtsUs = clock.latestVideoPtsUs,
                        latestAudioPtsUs = clock.latestAudioPtsUs,
                        lastMediaEmitElapsedRealtimeNs = clock.lastMediaEmitElapsedRealtimeNs
                    )
                }.takeIf { source.isStreaming }
            )
        }
        .stateIn(scope, SharingStarted.Eagerly, RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null))

    /**
     * Request an IDR from an already user-authorized active stream.
     *
     * This never starts projection, changes capture scope, or exposes media.
     * It exists so an authorized local measurement adapter can bound sealed
     * media latency on devices that do not honor the configured I-frame cadence.
     */
    public fun requestSyncFrame() {
        Handler(Looper.getMainLooper()).post { module.requestKeyFrame() }
    }

    /** Creates a capture attempt; the caller must subsequently obtain system consent. */
    public fun beginUserCapture(context: Context, permissionEducationShown: Boolean) {
        Handler(Looper.getMainLooper()).post {
            module.requestUserCapture(context, permissionEducationShown)
        }
    }

    /** Supplies the MediaProjection consent returned by the system dialog. */
    public fun submitProjectionPermission(startAttemptId: String, permissionIntent: Intent) {
        Handler(Looper.getMainLooper()).post { module.startProjection(startAttemptId, permissionIntent) }
    }

    /** Cancels the pending capture attempt after the user declines system consent. */
    public fun rejectProjectionPermission(startAttemptId: String) {
        Handler(Looper.getMainLooper()).post { module.sendEvent(RtspEvent.CastPermissionsDenied(startAttemptId)) }
    }

    /** Stops only the active user-authorized RTSP session. */
    public fun stopUserCapture() {
        Handler(Looper.getMainLooper()).post { module.stopStream("User action: V5 media session") }
    }
}
