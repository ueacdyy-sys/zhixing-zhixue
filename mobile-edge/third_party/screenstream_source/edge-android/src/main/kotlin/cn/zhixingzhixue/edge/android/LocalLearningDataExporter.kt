package cn.zhixingzhixue.edge.android

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import java.time.OffsetDateTime
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * User-initiated, local-only data export.  It intentionally excludes raw
 * screen/first-person media, pairing credentials, API secrets and device IDs.
 */
public object LocalLearningDataExporter {
    public suspend fun exportJson(
        context: Context,
        candidates: List<CandidateCard>,
        graph: KnowledgeGraphSnapshot,
        responses: List<StudentLearningResponse>,
        graphEvents: List<KnowledgeGraphEventSummary>,
    ): String = withContext(Dispatchers.IO) {
        val payload = JSONObject()
            .put("schema_version", "zhixing_local_learning_export.v1")
            .put("exported_at", OffsetDateTime.now().toString())
            .put("scope", JSONObject().put("raw_media", false).put("credentials", false).put("device_identifiers", false))
            .put("candidate_evidence", JSONArray().also { output ->
                candidates.forEach { card ->
                    output.put(JSONObject()
                        .put("topic_excerpt", card.displayExcerpt)
                        .put("source", card.source.name)
                        .put("visit_id", card.visitId)
                        .put("time_range_pts_ns", JSONObject().put("start", card.startPtsNs).put("end", card.endPtsNs))
                        .put("evidence_refs", JSONArray(card.evidenceRefs.map { it.value }))
                        .put("l1_eligible", card.isL1Eligible))
                }
            })
            .put("student_learning_responses", JSONArray().also { output ->
                responses.forEach { response ->
                    output.put(JSONObject()
                        .put("content_id", response.contentId)
                        .put("source", response.source.name)
                        .put("visit_id", response.visitId)
                        .put("stage", response.stage.name)
                        .put("body", response.body)
                        .put("recorded_at", response.recordedAt.toString())
                        .put("evidence_refs", JSONArray(response.evidenceRefs.map { it.value })))
                }
            })
            .put("knowledge_graph", JSONObject()
                .put("nodes", JSONArray().also { output -> graph.nodes.forEach { node -> output.put(JSONObject().put("id", node.id.value).put("label", node.label).put("note", node.note).put("evidence_refs", JSONArray(node.evidenceRefs.map { it.value }))) } })
                .put("edges", JSONArray().also { output -> graph.edges.forEach { edge -> output.put(JSONObject().put("from", edge.from.value).put("to", edge.to.value).put("relationship", edge.relationship.name).put("evidence_refs", JSONArray(edge.evidenceRefs.map { it.value }))) } }))
            .put("graph_audit", JSONArray().also { output -> graphEvents.forEach { event -> output.put(JSONObject().put("entity_kind", event.entityKind).put("operation", event.operation).put("state", event.state).put("occurred_at", event.occurredAt)) } })
        val name = "zhixing-local-learning-${System.currentTimeMillis()}.json"
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, "application/json")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
        }
        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) else MediaStore.Files.getContentUri("external")
        val uri = context.contentResolver.insert(collection, values) ?: throw IllegalStateException("local_export_destination_unavailable")
        try {
            context.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { it.write(payload.toString(2)) }
                ?: throw IllegalStateException("local_export_destination_unavailable")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0)
                context.contentResolver.update(uri, values, null, null)
            }
            name
        } catch (error: Exception) {
            context.contentResolver.delete(uri, null, null)
            throw error
        }
    }
}
