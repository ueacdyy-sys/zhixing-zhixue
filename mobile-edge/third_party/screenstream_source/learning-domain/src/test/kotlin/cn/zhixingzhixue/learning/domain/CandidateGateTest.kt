package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class CandidateGateTest {
    private val now: OffsetDateTime = OffsetDateTime.parse("2026-07-18T10:00:00+08:00")
    private val window = EvidenceWindow(now, now.plusSeconds(1), AudioCompleteness.NOT_AVAILABLE, TimeQuality.UNCERTAIN)

    @Test
    fun `keyframe OCR remains candidate only`() {
        val candidate = CandidateGate.fromKeyframeOcr(
            CandidateId("candidate-1"), MobileSessionId("session-1"), CaptureId("capture-1"), window,
            listOf(LocalEvidenceRef("local://evidence/frame-1")), "线性代数"
        )

        assertEquals(CandidateStatus.CANDIDATE_ONLY, candidate?.status)
        assertEquals(MobileEvidenceSource.MOBILE_SCREEN_KEYFRAME_OCR, candidate?.source)
    }

    @Test
    fun `missing OCR cannot create candidate`() {
        val candidate = CandidateGate.fromKeyframeOcr(
            CandidateId("candidate-1"), MobileSessionId("session-1"), CaptureId("capture-1"), window,
            listOf(LocalEvidenceRef("local://evidence/frame-1")), null
        )

        assertNull(candidate)
    }
}
