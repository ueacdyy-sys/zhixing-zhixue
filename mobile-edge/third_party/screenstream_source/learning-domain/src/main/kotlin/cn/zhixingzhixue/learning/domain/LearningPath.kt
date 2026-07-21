package cn.zhixingzhixue.learning.domain

/** Voluntary learning conversion stages from PPT L0–L4. */
public enum class LearningStage {
    L0_CANDIDATE,
    L1_CONCEPT_BRIEF,
    L2_EXPLORATION,
    L3_GUIDED_PRACTICE,
    L4_SELF_PRACTICE,
}

/** Only an explicit student action may advance this state. */
public enum class StudentLearningAction {
    VIEW_EVIDENCE,
    OPEN_L1_CONCEPT_BRIEF,
    OPEN_L2_EXPLORATION,
    START_L3_GUIDED_PRACTICE,
    START_L4_SELF_PRACTICE,
}

/** A candidate cannot become learning content until a controlled resource resolves it. */
public enum class KnowledgeResourceAvailability {
    UNRESOLVED,
    AVAILABLE,
    REJECTED,
}

public data class LearningPathState(
    val stage: LearningStage,
)

public data class LearningPathTransition(
    val state: LearningPathState,
    val accepted: Boolean,
    val reason: String,
)

public object LearningPathReducer {
    /**
     * Advance only one voluntary step. Dwell, notifications, OCR/ASR/VLM text
     * and engagement facts are intentionally absent from this boundary.
     */
    public fun reduce(
        current: LearningPathState,
        action: StudentLearningAction,
        hasCompleteCandidateEvidence: Boolean,
        resourceAvailability: KnowledgeResourceAvailability,
    ): LearningPathTransition {
        if (action == StudentLearningAction.VIEW_EVIDENCE) {
            return LearningPathTransition(current, accepted = true, reason = "EVIDENCE_VIEWED")
        }
        if (!hasCompleteCandidateEvidence) {
            return LearningPathTransition(current, accepted = false, reason = "COMPLETE_CANDIDATE_EVIDENCE_REQUIRED")
        }
        if (resourceAvailability != KnowledgeResourceAvailability.AVAILABLE) {
            return LearningPathTransition(current, accepted = false, reason = "CONTROLLED_KNOWLEDGE_RESOURCE_REQUIRED")
        }
        val target = when (action) {
            StudentLearningAction.OPEN_L1_CONCEPT_BRIEF -> LearningStage.L1_CONCEPT_BRIEF
            StudentLearningAction.OPEN_L2_EXPLORATION -> LearningStage.L2_EXPLORATION
            StudentLearningAction.START_L3_GUIDED_PRACTICE -> LearningStage.L3_GUIDED_PRACTICE
            StudentLearningAction.START_L4_SELF_PRACTICE -> LearningStage.L4_SELF_PRACTICE
            StudentLearningAction.VIEW_EVIDENCE -> current.stage
        }
        val expectedCurrent = when (target) {
            LearningStage.L1_CONCEPT_BRIEF -> LearningStage.L0_CANDIDATE
            LearningStage.L2_EXPLORATION -> LearningStage.L1_CONCEPT_BRIEF
            LearningStage.L3_GUIDED_PRACTICE -> LearningStage.L2_EXPLORATION
            LearningStage.L4_SELF_PRACTICE -> LearningStage.L3_GUIDED_PRACTICE
            LearningStage.L0_CANDIDATE -> current.stage
        }
        if (current.stage != expectedCurrent) {
            return LearningPathTransition(current, accepted = false, reason = "VOLUNTARY_STAGE_ORDER_REQUIRED")
        }
        return LearningPathTransition(LearningPathState(target), accepted = true, reason = "STUDENT_ACTION_ACCEPTED")
    }
}
