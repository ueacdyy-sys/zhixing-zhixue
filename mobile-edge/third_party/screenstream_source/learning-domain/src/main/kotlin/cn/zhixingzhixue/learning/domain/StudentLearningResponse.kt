package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime

/**
 * A student's explicit response inside an already opened PC learning package.
 *
 * It is deliberately separate from candidate-card receipts: a response records
 * what the student chose to write, not interest, mastery, correctness or a
 * change in L0-L4 stage.
 */
public data class StudentLearningResponse(
    val resultId: String,
    val contentId: String,
    val visitId: String,
    val source: CandidateMediaSource,
    val evidenceRefs: List<LocalEvidenceRef>,
    val stage: LearningStage,
    val body: String,
    val recordedAt: OffsetDateTime,
) {
    init {
        require(resultId.isNotBlank()) { "learning_response_result_required" }
        require(contentId.isNotBlank()) { "learning_response_content_required" }
        require(visitId.isNotBlank()) { "learning_response_visit_required" }
        require(evidenceRefs.isNotEmpty()) { "learning_response_evidence_required" }
        require(evidenceRefs.distinct().size == evidenceRefs.size) { "learning_response_evidence_duplicate" }
        require(stage == LearningStage.L3_GUIDED_PRACTICE || stage == LearningStage.L4_SELF_PRACTICE) {
            "learning_response_stage_invalid"
        }
        require(body.trim().isNotEmpty()) { "learning_response_body_required" }
    }
}
