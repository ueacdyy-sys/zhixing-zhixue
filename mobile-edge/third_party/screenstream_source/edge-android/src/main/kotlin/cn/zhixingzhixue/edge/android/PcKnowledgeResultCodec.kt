package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.domain.KnowledgeAssociation
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
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
}
