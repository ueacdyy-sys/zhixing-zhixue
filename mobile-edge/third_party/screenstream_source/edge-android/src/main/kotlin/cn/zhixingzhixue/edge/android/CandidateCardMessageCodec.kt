package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateCardGate
import cn.zhixingzhixue.learning.domain.CandidateCardId
import cn.zhixingzhixue.learning.domain.CandidateEvidenceFact
import cn.zhixingzhixue.learning.domain.CandidateEvidenceLane
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import org.json.JSONObject

/** Shared decoder for ADB diagnostics and the formal paired-PC outbox. */
public object CandidateCardMessageCodec {
    public fun decode(document: JSONObject): CandidateCard? = runCatching {
        if (
            document.optString("schema_version") != "candidate_card.v1" ||
            document.optString("classification") != "CANDIDATE_ONLY" ||
            document.optString("source_context") !in setOf("PHONE_DAILY", "GLASSES_FIRST_PERSON")
        ) {
            return null
        }
        val range = document.getJSONObject("media_range")
        val facts = document.getJSONArray("facts").let { entries ->
            List(entries.length()) { index ->
                entries.getJSONObject(index).let { fact ->
                    CandidateEvidenceFact(
                        CandidateEvidenceLane.valueOf(fact.getString("lane")),
                        fact.getString("text").take(MAX_FACT_CHARS),
                    )
                }
            }
        }
        val refs = document.getJSONArray("facts").let { entries ->
            List(entries.length()) { index -> LocalEvidenceRef(entries.getJSONObject(index).getString("evidence_uri")) }
        }
        CandidateCardGate.fromTrimodalEvidence(
            id = CandidateCardId(document.getString("card_id")),
            captureId = CaptureId(document.getString("window_id")),
            visitId = document.getString("visit_id"),
            startPtsNs = range.getLong("start_pts_ns"),
            endPtsNs = range.getLong("end_pts_ns"),
            evidenceRefs = refs,
            facts = facts,
            displayExcerpt = document.getString("display_excerpt").take(MAX_EXCERPT_CHARS),
            source = when (document.getString("source_context")) {
                "PHONE_DAILY" -> CandidateMediaSource.PHONE_SCREEN
                "GLASSES_FIRST_PERSON" -> CandidateMediaSource.GLASSES_FIRST_PERSON
                else -> return null
            },
            isL1Eligible = document.optBoolean("can_offer_l1", true),
        )
    }.getOrNull()

    private const val MAX_FACT_CHARS: Int = 240
    private const val MAX_EXCERPT_CHARS: Int = 240
}
