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
    val action: StudentReceiptAction,
    val recordedAt: OffsetDateTime
) {
    init {
        require((captureId == null) != (evidenceCardId == null)) { "exactly_one_evidence_reference_required" }
    }
}
