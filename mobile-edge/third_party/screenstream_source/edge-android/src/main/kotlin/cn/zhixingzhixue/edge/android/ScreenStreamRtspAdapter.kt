package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.application.MediaTransportPort
import cn.zhixingzhixue.learning.application.MediaTransportState
import cn.zhixingzhixue.learning.application.MediaTransportStatus
import info.dvkr.screenstream.rtsp.RtspTransportFacade
import info.dvkr.screenstream.rtsp.RtspTransportStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

/**
 * Marker for the only permitted ScreenStream integration point. Its concrete
 * implementation is added after the RTSP facade has a tested public contract.
 * No business object may import ScreenStream internals directly.
 */
public class ScreenStreamRtspAdapter(facade: RtspTransportFacade) : MediaTransportPort {
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override val state: StateFlow<MediaTransportState> = facade.state
        .map { transport ->
            MediaTransportState(
                status = transport.status.toBusinessStatus(),
                sessionId = null,
                captureId = null,
                startedAt = null,
                deviceAudioAvailable = transport.deviceAudioAvailable,
                activeConsumerCount = transport.activeConsumerCount,
                errorCode = transport.failureCode
            )
        }
        .stateIn(
            scope,
            SharingStarted.Eagerly,
            MediaTransportState(MediaTransportStatus.IDLE, null, null, null, false, 0, null)
        )

    private fun RtspTransportStatus.toBusinessStatus(): MediaTransportStatus = when (this) {
        RtspTransportStatus.IDLE -> MediaTransportStatus.IDLE
        RtspTransportStatus.STARTING -> MediaTransportStatus.WAITING_FOR_USER_PERMISSION
        RtspTransportStatus.WAITING_FOR_USER_PERMISSION -> MediaTransportStatus.WAITING_FOR_USER_PERMISSION
        RtspTransportStatus.STREAMING -> MediaTransportStatus.STREAMING
        RtspTransportStatus.STREAMING_NO_CONSUMER -> MediaTransportStatus.DEGRADED
        RtspTransportStatus.ERROR -> MediaTransportStatus.ERROR
    }
}
