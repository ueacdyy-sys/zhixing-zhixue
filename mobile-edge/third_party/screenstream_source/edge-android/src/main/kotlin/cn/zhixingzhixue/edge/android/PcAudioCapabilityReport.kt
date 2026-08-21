package cn.zhixingzhixue.edge.android

import info.dvkr.screenstream.rtsp.RtspAudioCapabilityStatus
import info.dvkr.screenstream.rtsp.RtspTransportSnapshot
import java.security.MessageDigest

/**
 * Immutable L0-only technical telemetry sent from the authorized handset to
 * its paired PC.  This is not a v2 AudioCapabilitySnapshot: it carries raw
 * transport facts so the PC can later perform its own authenticated range and
 * clock checks without treating an encoder as proof of semantic audio.
 */
public data class PcAudioCapabilityReport(
    val snapshotId: String,
    val captureGeneration: Long,
    val capturePath: String,
    val status: String,
    val applicationPackageId: String?,
    val restriction: String,
    val failureCode: String?,
    val videoPtsStartUs: Long,
    val videoPtsEndUs: Long,
    val audioPtsStartUs: Long?,
    val audioPtsEndUs: Long?,
    val sessionEpochId: String,
    val anchorElapsedRealtimeNs: Long,
    val syncErrorUs: Long?,
    val recoveryAttempt: Int,
) {
    /** The PC gateway retains this admission label; no code may upgrade it here. */
    public val admission: String = "L0_ONLY_NO_V2_CONSENT"

    public companion object {
        /**
         * Returns null until the running RTSP session has an actual monotonic
         * anchor and video PTS.  Missing timing is a gap to preserve, not data
         * to invent from a wall clock or an encoder state.
         */
        public fun fromTransport(
            sessionId: String,
            captureGeneration: Long,
            applicationPackageId: String?,
            transport: RtspTransportSnapshot,
        ): PcAudioCapabilityReport? {
            require(sessionId.isNotBlank()) { "capture_session_id_required" }
            require(captureGeneration > 0L) { "capture_generation_invalid" }
            val timing = transport.timing ?: return null
            val anchorNs = timing.anchorElapsedRealtimeNs ?: return null
            val videoPtsUs = timing.latestVideoPtsUs ?: return null
            val audio = transport.audioCapability
            val audioPtsUs = timing.latestAudioPtsUs.takeIf { audio.captureMode.name != "NONE" }
            val failureCode = audio.failureCode?.takeIf { it.isNotBlank() }
            val epochId = "rtsp-" + timing.sessionEpochId
            val snapshotId = listOf(
                "audio", captureGeneration, epochId, videoPtsUs, audioPtsUs ?: "none",
                audio.captureMode.name, audio.status.name, stableToken(failureCode),
            ).joinToString("-")
            return PcAudioCapabilityReport(
                snapshotId = snapshotId,
                captureGeneration = captureGeneration,
                capturePath = audio.captureMode.name,
                status = audio.status.name,
                applicationPackageId = applicationPackageId,
                restriction = restrictionFor(audio.status, failureCode),
                failureCode = failureCode,
                videoPtsStartUs = videoPtsUs,
                videoPtsEndUs = videoPtsUs,
                audioPtsStartUs = audioPtsUs,
                audioPtsEndUs = audioPtsUs,
                sessionEpochId = epochId,
                anchorElapsedRealtimeNs = anchorNs,
                // Raw latest audio/video PTS are not a synchronization sample.
                // Leave this unknown until the PC produces an explicit estimate.
                syncErrorUs = null,
                recoveryAttempt = 0,
            )
        }

        private fun restrictionFor(status: RtspAudioCapabilityStatus, failureCode: String?): String = when (status) {
            RtspAudioCapabilityStatus.NOT_REQUESTED,
            RtspAudioCapabilityStatus.CAPTURE_ACTIVE_UNVERIFIED -> "NONE"
            RtspAudioCapabilityStatus.UNRESOLVED -> when {
                failureCode?.contains("permission", ignoreCase = true) == true -> "PERMISSION_DENIED"
                failureCode?.contains("drm", ignoreCase = true) == true -> "DRM_PROTECTED"
                failureCode?.contains("policy", ignoreCase = true) == true -> "SYSTEM_POLICY"
                failureCode?.contains("application", ignoreCase = true) == true -> "APPLICATION_DISALLOWED"
                !failureCode.isNullOrBlank() -> "CAPTURE_FAILURE"
                else -> "UNKNOWN"
            }
        }

        private fun stableToken(value: String?): String {
            if (value.isNullOrBlank()) return "none"
            return MessageDigest.getInstance("SHA-256")
                .digest(value.toByteArray(Charsets.UTF_8))
                .joinToString("") { byte -> "%02x".format(byte) }
        }
    }
}
