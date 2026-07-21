package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime

public enum class StudentReceiptAction {
    SAVE,
    WATCH_LATER,
    DISMISS
}

public data class StudentReceipt(
    val captureId: CaptureId?,
    val evidenceCardId: EvidenceCardId?,
    /** Exact reference for the current phone candidate-card contract. */
    val candidateCardId: CandidateCardId? = null,
    val action: StudentReceiptAction,
    val recordedAt: OffsetDateTime
) {
    init {
        require(listOf(captureId, evidenceCardId, candidateCardId).count { it != null } == 1) {
            "exactly_one_evidence_reference_required"
        }
    }
}
