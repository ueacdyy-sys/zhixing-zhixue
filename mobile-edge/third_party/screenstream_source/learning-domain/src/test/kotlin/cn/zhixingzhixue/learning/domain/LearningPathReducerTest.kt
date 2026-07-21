package cn.zhixingzhixue.learning.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class LearningPathReducerTest {
    @Test
    fun `L stages advance only by explicit student action and a resolved resource`() {
        val l0 = LearningPathState(LearningStage.L0_CANDIDATE)
        val unresolved = LearningPathReducer.reduce(
            l0,
            StudentLearningAction.OPEN_L1_CONCEPT_BRIEF,
            hasCompleteCandidateEvidence = true,
            resourceAvailability = KnowledgeResourceAvailability.UNRESOLVED,
        )
        val l1 = LearningPathReducer.reduce(
            l0,
            StudentLearningAction.OPEN_L1_CONCEPT_BRIEF,
            hasCompleteCandidateEvidence = true,
            resourceAvailability = KnowledgeResourceAvailability.AVAILABLE,
        )
        val l2 = LearningPathReducer.reduce(
            l1.state,
            StudentLearningAction.OPEN_L2_EXPLORATION,
            hasCompleteCandidateEvidence = true,
            resourceAvailability = KnowledgeResourceAvailability.AVAILABLE,
        )

        assertFalse(unresolved.accepted)
        assertEquals(LearningStage.L0_CANDIDATE, unresolved.state.stage)
        assertTrue(l1.accepted)
        assertEquals(LearningStage.L1_CONCEPT_BRIEF, l1.state.stage)
        assertTrue(l2.accepted)
        assertEquals(LearningStage.L2_EXPLORATION, l2.state.stage)
    }

    @Test
    fun `L3 and L4 cannot be inferred from dwell or candidate evidence`() {
        val l0 = LearningPathState(LearningStage.L0_CANDIDATE)
        val directL3 = LearningPathReducer.reduce(
            l0,
            StudentLearningAction.START_L3_GUIDED_PRACTICE,
            hasCompleteCandidateEvidence = true,
            resourceAvailability = KnowledgeResourceAvailability.AVAILABLE,
        )
        val directL4 = LearningPathReducer.reduce(
            l0,
            StudentLearningAction.START_L4_SELF_PRACTICE,
            hasCompleteCandidateEvidence = true,
            resourceAvailability = KnowledgeResourceAvailability.AVAILABLE,
        )

        assertFalse(directL3.accepted)
        assertFalse(directL4.accepted)
        assertEquals(LearningStage.L0_CANDIDATE, directL3.state.stage)
        assertEquals(LearningStage.L0_CANDIDATE, directL4.state.stage)
    }
}
