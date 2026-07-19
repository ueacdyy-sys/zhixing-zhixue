package info.dvkr.screenstream.rtsp

import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import info.dvkr.screenstream.rtsp.internal.MasterClock

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
 * This facade intentionally exposes observation only. Projection permission and
 * start/stop remain in the explicit RTSP media-control UI, so a business use
 * case cannot start background capture without student action.
 */
public class RtspTransportFacade(private val module: RtspStreamingModule) {
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    public val state: StateFlow<RtspTransportSnapshot> = module.rtspStateFlow
        .map { source ->
            val consumerCount = source.serverClientStats.count { it.lastSentAtMs > 0L }
            val status = when {
                source.error != null -> RtspTransportStatus.ERROR
                source.waitingCastPermission -> RtspTransportStatus.WAITING_FOR_USER_PERMISSION
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
}
