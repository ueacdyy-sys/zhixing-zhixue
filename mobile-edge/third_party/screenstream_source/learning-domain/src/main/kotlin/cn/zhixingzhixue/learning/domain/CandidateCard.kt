package cn.zhixingzhixue.learning.domain

/** Identifier for the immutable phone-facing envelope of one fused media window. */
@JvmInline
public value class CandidateCardId(public val value: String)

/** The card never upgrades evidence into an interest or learning conclusion. */
public enum class CandidateCardClassification {
    CANDIDATE_ONLY,
}

/** Evidence source is explicit so phone screen and first-person sessions never mix silently. */
public enum class CandidateMediaSource {
    PHONE_SCREEN,
    GLASSES_FIRST_PERSON,
}

public enum class CandidateEvidenceLane {
    ASR,
    OCR,
    VLM,
}

/** A lane-specific excerpt with no cross-modal interpretation added by the phone. */
public data class CandidateEvidenceFact(
    val lane: CandidateEvidenceLane,
    val text: String,
) {
    init {
        require(text.isNotBlank()) { "candidate_fact_text_required" }
    }
}

/**
 * Immutable candidate evidence ready for a student to inspect on mobile.
 *
 * `isL1Eligible` means only that the student may receive an L1 entry prompt.
 * It does not mean the student is interested, has learned, or should enter a
 * later learning stage.
 */
public data class CandidateCard(
    val id: CandidateCardId,
    val captureId: CaptureId,
    val visitId: String,
    val startPtsNs: Long,
    val endPtsNs: Long,
    val evidenceRefs: List<LocalEvidenceRef>,
    val facts: List<CandidateEvidenceFact>,
    val displayExcerpt: String,
    val classification: CandidateCardClassification,
    val isL1Eligible: Boolean,
    val source: CandidateMediaSource = CandidateMediaSource.PHONE_SCREEN,
) {
    init {
        require(visitId.isNotBlank()) { "candidate_card_visit_required" }
        require(startPtsNs >= 0L && endPtsNs > startPtsNs) { "candidate_card_pts_invalid" }
        require(displayExcerpt.isNotBlank()) { "candidate_card_excerpt_required" }
        require(evidenceRefs.distinct().size == evidenceRefs.size) { "candidate_card_evidence_duplicate" }
        require(facts.map { it.lane }.toSet() == CandidateEvidenceLane.entries.toSet()) { "candidate_card_trimodal_facts_required" }
        require(classification == CandidateCardClassification.CANDIDATE_ONLY) { "candidate_card_must_remain_candidate_only" }
    }
}

public object CandidateCardGate {
    /**
     * L1 eligibility has no dwell-time, notification-count or inferred-interest
     * input. It follows only from a complete aligned ASR/OCR/VLM evidence set.
     */
    public fun fromTrimodalEvidence(
        id: CandidateCardId,
        captureId: CaptureId,
        visitId: String,
        startPtsNs: Long,
        endPtsNs: Long,
        evidenceRefs: List<LocalEvidenceRef>,
        facts: List<CandidateEvidenceFact>,
        displayExcerpt: String,
        source: CandidateMediaSource = CandidateMediaSource.PHONE_SCREEN,
        isL1Eligible: Boolean = true,
    ): CandidateCard? {
        if (
            evidenceRefs.size != CandidateEvidenceLane.entries.size ||
            facts.map { it.lane }.toSet() != CandidateEvidenceLane.entries.toSet() ||
            startPtsNs < 0L || endPtsNs <= startPtsNs ||
            visitId.isBlank() || displayExcerpt.isBlank()
        ) {
            return null
        }
        return CandidateCard(
            id = id,
            captureId = captureId,
            visitId = visitId,
            startPtsNs = startPtsNs,
            endPtsNs = endPtsNs,
            evidenceRefs = evidenceRefs,
            facts = facts,
            displayExcerpt = displayExcerpt.trim(),
            classification = CandidateCardClassification.CANDIDATE_ONLY,
            isL1Eligible = isL1Eligible,
            source = source,
        )
    }
}
