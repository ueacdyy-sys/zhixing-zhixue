package cn.zhixingzhixue.learning.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.assertNotNull

class CandidateCardGateTest {
    private val refs = listOf(
        LocalEvidenceRef("local://artifact/asr.json"),
        LocalEvidenceRef("local://artifact/ocr.json"),
        LocalEvidenceRef("local://artifact/vlm.json"),
    )

    @Test
    fun `complete trimodal card is candidate only and L1 eligible`() {
        val card = CandidateCardGate.fromTrimodalEvidence(
            id = CandidateCardId("card-1"),
            captureId = CaptureId("window-1"),
            visitId = "visit-1",
            startPtsNs = 10L,
            endPtsNs = 20L,
            evidenceRefs = refs,
            facts = listOf(
                CandidateEvidenceFact(CandidateEvidenceLane.ASR, "语音文本"),
                CandidateEvidenceFact(CandidateEvidenceLane.OCR, "屏幕文字"),
                CandidateEvidenceFact(CandidateEvidenceLane.VLM, "画面事实"),
            ),
            displayExcerpt = "语音文本",
        )

        assertNotNull(card)
        assertEquals(CandidateCardClassification.CANDIDATE_ONLY, card.classification)
        assertTrue(card.isL1Eligible)
        assertEquals("语音文本", card.displayExcerpt)
    }

    @Test
    fun `missing modality cannot create a card or L1 prompt`() {
        val card = CandidateCardGate.fromTrimodalEvidence(
            id = CandidateCardId("card-1"),
            captureId = CaptureId("window-1"),
            visitId = "visit-1",
            startPtsNs = 10L,
            endPtsNs = 20L,
            evidenceRefs = refs.take(2),
            facts = listOf(
                CandidateEvidenceFact(CandidateEvidenceLane.ASR, "语音文本"),
                CandidateEvidenceFact(CandidateEvidenceLane.OCR, "屏幕文字"),
            ),
            displayExcerpt = "语音文本",
        )

        assertNull(card)
    }

    @Test
    fun `first person evidence keeps its source and may remain sealed before L1 is offered`() {
        val card = CandidateCardGate.fromTrimodalEvidence(
            id = CandidateCardId("glasses-card-1"),
            captureId = CaptureId("glasses-window-1"),
            visitId = "glasses-visit-1",
            startPtsNs = 10L,
            endPtsNs = 20L,
            evidenceRefs = refs,
            facts = listOf(
                CandidateEvidenceFact(CandidateEvidenceLane.ASR, "现场语音"),
                CandidateEvidenceFact(CandidateEvidenceLane.OCR, "环境文字"),
                CandidateEvidenceFact(CandidateEvidenceLane.VLM, "第一视角画面事实"),
            ),
            displayExcerpt = "第一视角封存片段",
            source = CandidateMediaSource.GLASSES_FIRST_PERSON,
            isL1Eligible = false,
        )

        assertNotNull(card)
        assertEquals(CandidateMediaSource.GLASSES_FIRST_PERSON, card.source)
        assertTrue(!card.isL1Eligible)
    }
}
