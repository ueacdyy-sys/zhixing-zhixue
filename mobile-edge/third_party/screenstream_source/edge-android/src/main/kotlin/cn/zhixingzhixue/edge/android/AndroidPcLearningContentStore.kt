package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
import cn.zhixingzhixue.learning.domain.PcLearningContent
import cn.zhixingzhixue.learning.domain.TrustedLearningResource
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject

/** Persisted inbox for PC-generated learning content that is actually complete. */
public class AndroidPcLearningContentStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val items = MutableStateFlow(read())

    public fun observe(): StateFlow<List<PcLearningContentItem>> = items

    public fun accept(result: PcKnowledgeAnalysisResult) {
        val content = result.learningContent ?: return
        val item = PcLearningContentItem(result.resultId, result.visitId, result.source, content)
        val updated = (items.value.filterNot { it.resultId == item.resultId } + item)
            .sortedByDescending { it.resultId }
        preferences.edit().putString(ITEMS, encode(updated).toString()).apply()
        items.value = updated
    }

    private fun read(): List<PcLearningContentItem> = runCatching {
        decode(JSONArray(preferences.getString(ITEMS, "[]")))
    }.getOrDefault(emptyList())

    private fun encode(values: List<PcLearningContentItem>): JSONArray = JSONArray().also { output ->
        values.forEach { item ->
            val content = item.content
            output.put(
                JSONObject()
                    .put("result_id", item.resultId)
                    .put("visit_id", item.visitId)
                    .put("source", item.source.name)
                    .put("content_id", content.contentId)
                    .put("concept_title", content.conceptTitle)
                    .put("concept_brief", content.conceptBrief)
                    .put("background", content.background)
                    .put("worked_example", content.workedExample)
                    .put("guided_practice", content.guidedPractice)
                    .put("self_practice", content.selfPractice)
                    .put("trusted_resources", JSONArray(content.trustedResources.map { resource ->
                        JSONObject().put("title", resource.title).put("publisher", resource.publisher).put("url", resource.url)
                    }))
                    .put("evidence_refs", JSONArray(content.evidenceRefs.map { it.value })),
            )
        }
    }

    private fun decode(values: JSONArray): List<PcLearningContentItem> = List(values.length()) { index ->
        val value = values.getJSONObject(index)
        PcLearningContentItem(
            resultId = value.getString("result_id"),
            visitId = value.getString("visit_id"),
            source = value.optString("source", CandidateMediaSource.PHONE_SCREEN.name)
                .let { CandidateMediaSource.valueOf(it) },
            content = PcLearningContent(
                contentId = value.getString("content_id"),
                conceptTitle = value.getString("concept_title"),
                conceptBrief = value.getString("concept_brief"),
                background = value.getString("background"),
                workedExample = value.getString("worked_example"),
                guidedPractice = value.getString("guided_practice"),
                selfPractice = value.getString("self_practice"),
                trustedResources = value.getJSONArray("trusted_resources").let { resources ->
                    List(resources.length()) { resourceIndex ->
                        resources.getJSONObject(resourceIndex).let { resource ->
                            TrustedLearningResource(resource.getString("title"), resource.getString("publisher"), resource.getString("url"))
                        }
                    }
                },
                evidenceRefs = value.getJSONArray("evidence_refs").let { refs ->
                    List(refs.length()) { refIndex -> LocalEvidenceRef(refs.getString(refIndex)) }
                },
            ),
        )
    }

    private companion object {
        private const val PREFERENCES: String = "zhixing_pc_learning_content_v1"
        private const val ITEMS: String = "items"
    }
}

public data class PcLearningContentItem(
    val resultId: String,
    val visitId: String,
    val source: CandidateMediaSource,
    val content: PcLearningContent,
)
