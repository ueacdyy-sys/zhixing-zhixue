package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.domain.KnowledgeAssociation
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
import cn.zhixingzhixue.learning.domain.PcLearningContent
import cn.zhixingzhixue.learning.domain.TrustedLearningResource
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime

/** Versioned decoder for a PC result delivered over the formal local-LAN path. */
public object PcKnowledgeResultCodec {
    public const val SCHEMA_VERSION: String = "pc_knowledge_analysis_result.v1"

    public fun decode(raw: String): PcKnowledgeAnalysisResult {
        val document = JSONObject(raw)
        require(document.getString("schema_version") == SCHEMA_VERSION) {
            "pc_knowledge_result_schema_unsupported"
        }
        return PcKnowledgeAnalysisResult(
            resultId = document.getString("result_id"),
            sessionId = MobileSessionId(document.getString("session_id")),
            visitId = document.getString("visit_id"),
            createdAt = OffsetDateTime.parse(document.getString("created_at")),
            evidenceRefs = references(document.getJSONArray("evidence_refs")),
            associations = associations(document.getJSONArray("associations")),
            learningContent = document.optJSONObject("learning_content")?.let(::learningContent),
            source = source(document.optString("source_context", "PHONE_DAILY")),
        )
    }

    private fun associations(values: JSONArray): List<KnowledgeAssociation> = List(values.length()) { index ->
        val item = values.getJSONObject(index)
        KnowledgeAssociation(
            topic = item.getString("topic"),
            subjectTag = item.getString("subject_tag"),
            relationship = KnowledgeRelationship.valueOf(item.getString("relationship")),
            confidence = item.getDouble("confidence"),
            evidenceRefs = references(item.getJSONArray("evidence_refs")),
        )
    }

    private fun references(values: JSONArray): List<LocalEvidenceRef> =
        List(values.length()) { index -> LocalEvidenceRef(values.getString(index)) }

    private fun learningContent(value: JSONObject): PcLearningContent = PcLearningContent(
        contentId = value.getString("content_id"),
        conceptTitle = value.getString("concept_title"),
        conceptBrief = value.getString("concept_brief"),
        background = value.getString("background"),
        workedExample = value.getString("worked_example"),
        guidedPractice = value.getString("guided_practice"),
        selfPractice = value.getString("self_practice"),
        trustedResources = value.getJSONArray("trusted_resources").let { resources ->
            List(resources.length()) { index ->
                resources.getJSONObject(index).let { resource ->
                    TrustedLearningResource(
                        title = resource.getString("title"),
                        publisher = resource.getString("publisher"),
                        url = resource.getString("url"),
                    )
                }
            }
        },
        evidenceRefs = references(value.getJSONArray("evidence_refs")),
    )

    private fun source(value: String): CandidateMediaSource = when (value) {
        "PHONE_DAILY", "PHONE_SCREEN" -> CandidateMediaSource.PHONE_SCREEN
        "GLASSES_FIRST_PERSON" -> CandidateMediaSource.GLASSES_FIRST_PERSON
        else -> throw IllegalArgumentException("pc_analysis_source_context_invalid")
    }
}
