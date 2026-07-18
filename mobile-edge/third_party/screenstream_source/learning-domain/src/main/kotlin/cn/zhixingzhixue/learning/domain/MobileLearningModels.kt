package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime

@JvmInline
public value class MobileSessionId(public val value: String)

@JvmInline
public value class CaptureId(public val value: String)

@JvmInline
public value class EvidenceCardId(public val value: String)

@JvmInline
public value class CandidateId(public val value: String)

@JvmInline
public value class LocalEvidenceRef(public val value: String) {
    init {
        require(value.startsWith("local://")) { "local_evidence_ref_required" }
    }
}

/**
 * A phone-side candidate is deliberately not an interest, knowledge, diagnostic,
 * practice, or recommendation conclusion.
 */
public enum class CandidateStatus {
    NO_CANDIDATE,
    CANDIDATE_ONLY,
    SEMANTIC_ANALYSIS_PENDING,
    EXCLUDED
}

public enum class MobileEvidenceSource {
    MOBILE_SCREEN_KEYFRAME_OCR,
    CONTINUOUS_MEDIA
}

public enum class AudioCompleteness {
    NOT_AVAILABLE,
    PARTIAL,
    SYNCHRONIZED
}

public enum class TimeQuality {
    UNCERTAIN,
    SYNCHRONIZED
}

public data class EvidenceWindow(
    val startedAt: OffsetDateTime,
    val endedAt: OffsetDateTime,
    val audioCompleteness: AudioCompleteness,
    val timeQuality: TimeQuality
) {
    init {
        require(!endedAt.isBefore(startedAt)) { "evidence_window_end_before_start" }
    }
}

public data class KnowledgePointCandidate(
    val id: CandidateId,
    val sessionId: MobileSessionId,
    val captureId: CaptureId,
    val status: CandidateStatus,
    val source: MobileEvidenceSource,
    val evidenceWindow: EvidenceWindow,
    val evidenceRefs: List<LocalEvidenceRef>,
    val ocrExcerpt: String?
) {
    init {
        require(status != CandidateStatus.CANDIDATE_ONLY || evidenceRefs.isNotEmpty()) { "candidate_evidence_required" }
        require(status != CandidateStatus.CANDIDATE_ONLY || !ocrExcerpt.isNullOrBlank()) { "candidate_ocr_required" }
    }
}

public enum class LearningDeviceType {
    PHONE,
    PC,
    EEG_GLASSES,
    WATCH
}

public enum class DeviceConnectionState {
    DISCOVERED,
    CONNECTED,
    DEGRADED,
    DISCONNECTED
}

@JvmInline
public value class DeviceId(public val value: String)

public data class DeviceConnection(
    val deviceId: DeviceId,
    val type: LearningDeviceType,
    val state: DeviceConnectionState,
    val capabilityNames: Set<String>,
    val observedAt: OffsetDateTime
)

/** A time measurement, not a claim that two device clocks are permanently aligned. */
public data class SyncAnchor(
    val peer: DeviceId,
    val measuredAt: OffsetDateTime,
    val clockOffsetMs: Long,
    val roundTripMs: Long,
    val isUsable: Boolean
)

public enum class MobileSessionStatus {
    ACTIVE,
    PAUSED,
    CLOSED
}

public data class MobileLearningSession(
    val id: MobileSessionId,
    val startedAt: OffsetDateTime,
    val status: MobileSessionStatus
)
