package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime
import kotlin.test.Test
import kotlin.test.assertFailsWith

public class StudentLearningResponseTest {
    @Test
    public fun `only L3 and L4 accept an explicit learning response`() {
        StudentLearningResponse(
            resultId = "pc-result-1",
            contentId = "pc-content-1",
            visitId = "visit-1",
            source = CandidateMediaSource.PHONE_SCREEN,
            evidenceRefs = listOf(LocalEvidenceRef("local://evidence-1")),
            stage = LearningStage.L3_GUIDED_PRACTICE,
            body = "我选择了一个案例并说明理由。",
            recordedAt = OffsetDateTime.parse("2026-07-23T09:30:00+08:00"),
        )

        assertFailsWith<IllegalArgumentException> {
            StudentLearningResponse(
                resultId = "pc-result-1",
                contentId = "pc-content-1",
                visitId = "visit-1",
                source = CandidateMediaSource.PHONE_SCREEN,
                evidenceRefs = listOf(LocalEvidenceRef("local://evidence-1")),
                stage = LearningStage.L2_EXPLORATION,
                body = "不应在 L2 保存自主回应。",
                recordedAt = OffsetDateTime.parse("2026-07-23T09:30:00+08:00"),
            )
        }
    }

    @Test
    public fun `blank response is rejected without creating a learning record`() {
        assertFailsWith<IllegalArgumentException> {
            StudentLearningResponse(
                resultId = "pc-result-1",
                contentId = "pc-content-1",
                visitId = "visit-1",
                source = CandidateMediaSource.PHONE_SCREEN,
                evidenceRefs = listOf(LocalEvidenceRef("local://evidence-1")),
                stage = LearningStage.L4_SELF_PRACTICE,
                body = "   ",
                recordedAt = OffsetDateTime.parse("2026-07-23T09:30:00+08:00"),
            )
        }
    }
}
