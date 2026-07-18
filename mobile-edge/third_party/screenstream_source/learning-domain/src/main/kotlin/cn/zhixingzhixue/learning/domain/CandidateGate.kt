package cn.zhixingzhixue.learning.domain

public object CandidateGate {
    /**
     * Mirrors the local-hub conservative rule: a single/OCR-only frame never
     * upgrades to a learning, interest, or knowledge conclusion.
     */
    public fun fromKeyframeOcr(
        id: CandidateId,
        sessionId: MobileSessionId,
        captureId: CaptureId,
        evidenceWindow: EvidenceWindow,
        evidenceRefs: List<LocalEvidenceRef>,
        ocrExcerpt: String?
    ): KnowledgePointCandidate? {
        if (evidenceRefs.isEmpty() || ocrExcerpt.isNullOrBlank()) return null
        return KnowledgePointCandidate(
            id = id,
            sessionId = sessionId,
            captureId = captureId,
            status = CandidateStatus.CANDIDATE_ONLY,
            source = MobileEvidenceSource.MOBILE_SCREEN_KEYFRAME_OCR,
            evidenceWindow = evidenceWindow,
            evidenceRefs = evidenceRefs,
            ocrExcerpt = ocrExcerpt.trim()
        )
    }
}
