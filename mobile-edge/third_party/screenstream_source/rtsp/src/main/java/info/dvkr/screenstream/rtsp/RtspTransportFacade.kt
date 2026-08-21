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

/** The requested Android audio path; it is not a claim about media semantics. */
public enum class RtspAudioCaptureMode {
    NONE,
    PLAYBACK,
    MICROPHONE,
    MIXED
}

/**
 * Transport-level audio evidence.  ACTIVE is deliberately unverified: an
 * app may still suppress playback capture, use DRM, or emit an unsynchronised
 * track.  Only the later v2 AudioCapabilitySnapshot may claim same-source
 * semantic audio after its own hashes and clock samples are present.
 */
public enum class RtspAudioCapabilityStatus {
    NOT_REQUESTED,
    CAPTURE_ACTIVE_UNVERIFIED,
    UNRESOLVED
}

/** Encoded output copied at the codec boundary; no RTSP packet or cleartext fallback is exposed. */
public enum class RtspEncodedTrack { VIDEO, AUDIO }

/** Codec declaration for the private v2 egress; bytes alone are never guessed. */
public enum class RtspEncodedVideoCodec { H264, H265, AV1 }

public data class RtspEncodedFrame(
    val track: RtspEncodedTrack,
    val ptsUs: Long,
    /** Codec callbacks expose a start PTS only; a session adapter must derive a bounded end range. */
    val durationUs: Long?,
    val isKeyFrame: Boolean,
    val bytes: ByteArray,
    /** Required for video. Audio remains unresolved until a separate capability contract verifies it. */
    val videoCodec: RtspEncodedVideoCodec? = null,
    /** Annex-B parameter sets copied only with an H.264 keyframe for PC-local decoding. */
    val videoCodecConfigAnnexB: ByteArray? = null,
)

public fun interface RtspEncodedFrameSink {
    /** The sink must return quickly and must not retain [frame.bytes] without copying. */
    public fun onEncodedFrame(frame: RtspEncodedFrame)
}

public data class RtspAudioCapabilitySnapshot(
    val captureMode: RtspAudioCaptureMode,
    val status: RtspAudioCapabilityStatus,
    val failureCode: String?
) {
    public companion object {
        public fun fromRuntime(
            microphoneRequested: Boolean,
            devicePlaybackRequested: Boolean,
            encoderRunning: Boolean,
            captureDisabled: Boolean,
            failureCode: String?
        ): RtspAudioCapabilitySnapshot {
            val mode = when {
                microphoneRequested && devicePlaybackRequested -> RtspAudioCaptureMode.MIXED
                devicePlaybackRequested -> RtspAudioCaptureMode.PLAYBACK
                microphoneRequested -> RtspAudioCaptureMode.MICROPHONE
                else -> RtspAudioCaptureMode.NONE
            }
            return when {
                mode == RtspAudioCaptureMode.NONE -> RtspAudioCapabilitySnapshot(
                    mode, RtspAudioCapabilityStatus.NOT_REQUESTED, null
                )
                captureDisabled || !failureCode.isNullOrBlank() -> RtspAudioCapabilitySnapshot(
                    mode, RtspAudioCapabilityStatus.UNRESOLVED, failureCode ?: "audio_capture_disabled"
                )
                encoderRunning -> RtspAudioCapabilitySnapshot(
                    mode, RtspAudioCapabilityStatus.CAPTURE_ACTIVE_UNVERIFIED, null
                )
                else -> RtspAudioCapabilitySnapshot(
                    mode, RtspAudioCapabilityStatus.UNRESOLVED, "audio_encoder_not_running"
                )
            }
        }
    }
}

public data class RtspTransportSnapshot(
    val status: RtspTransportStatus,
    val activeConsumerCount: Int,
    val endpoint: String?,
    val deviceAudioAvailable: Boolean,
    val failureCode: String?,
    val audioCapability: RtspAudioCapabilitySnapshot = RtspAudioCapabilitySnapshot.fromRuntime(
        microphoneRequested = false,
        devicePlaybackRequested = false,
        encoderRunning = false,
        captureDisabled = false,
        failureCode = null
    ),
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
                audioCapability = RtspAudioCapabilitySnapshot.fromRuntime(
                    microphoneRequested = source.microphoneAudioRequested,
                    devicePlaybackRequested = source.devicePlaybackAudioRequested,
                    encoderRunning = source.isStreaming && source.selectedAudioEncoder != null && !source.audioCaptureDisabled,
                    captureDisabled = source.audioCaptureDisabled,
                    failureCode = source.audioCaptureFailureCode,
                ),
                startAttemptId = source.startAttemptId,
                timing = currentTimingSnapshot().takeIf { source.isStreaming }
            )
        }
        .stateIn(scope, SharingStarted.Eagerly, RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null))

    /**
     * Reads the current RTSP master clock without controlling the transport.
     * A consumer that polls a StateFlow must use this instead of treating a
     * previous status emission as a fresh media timestamp.
     */
    public fun currentTimingSnapshot(): RtspTransportTimingSnapshot {
        val clock = MasterClock.snapshot()
        return RtspTransportTimingSnapshot(
            sessionEpochId = clock.sessionEpochId,
            anchorElapsedRealtimeNs = clock.anchorElapsedRealtimeNs,
            anchorWallClockMs = clock.anchorWallClockMs,
            latestVideoPtsUs = clock.latestVideoPtsUs,
            latestAudioPtsUs = clock.latestAudioPtsUs,
            lastMediaEmitElapsedRealtimeNs = clock.lastMediaEmitElapsedRealtimeNs
        )
    }

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

    /**
     * Opens or closes only the paired-PC media egress gate for an already
     * authorized projection. Closing it drops frames before any RTSP client
     * receives them; it does not stop MediaProjection or ask the learner to
     * grant consent again.
     */
    public fun setPairedPcOutputAllowed(allowed: Boolean) {
        Handler(Looper.getMainLooper()).post { module.setPairedPcOutputAllowed(allowed) }
    }

    /** Installs the v2 sink only after edge-android has a real session binding. */
    public fun setEncodedFrameSink(sink: RtspEncodedFrameSink?) {
        Handler(Looper.getMainLooper()).post { module.setEncodedFrameSink(sink) }
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
