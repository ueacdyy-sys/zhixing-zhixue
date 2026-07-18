package info.dvkr.screenstream.rtsp

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

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
    val failureCode: String?
)

/**
 * This facade intentionally exposes observation only. Projection permission and
 * start/stop remain in the explicit RTSP media-control UI, so a business use
 * case cannot start background capture without student action.
 */
public class RtspTransportFacade(module: RtspStreamingModule) {
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
                failureCode = source.error?.javaClass?.simpleName
            )
        }
        .stateIn(scope, SharingStarted.Eagerly, RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null))
}
