package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.LearningResponsePort
import cn.zhixingzhixue.learning.domain.LearningStage
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import java.time.OffsetDateTime
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import org.json.JSONObject

/**
 * Local-only journal for student writing in L3/L4.
 *
 * This is not a teacher submission queue and does not grade, infer, or advance
 * a learning stage. A future export adapter can decide which explicitly
 * approved records are eligible to leave the device.
 */
public class AndroidLearningResponseStore(context: Context) : LearningResponsePort {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val responses = MutableStateFlow(read())

    override fun observe(resultId: String, contentId: String): Flow<List<StudentLearningResponse>> =
        responses.map { values -> values.filter { it.resultId == resultId && it.contentId == contentId } }

    override suspend fun record(response: StudentLearningResponse) {
        val updated = (responses.value + response).sortedBy { it.recordedAt }
        preferences.edit().putString(RESPONSES, encode(updated).toString()).apply()
        responses.value = updated
    }

    /** Explicitly recorded student responses only; never inferred progress. */
    public fun snapshot(): List<StudentLearningResponse> = responses.value

    private fun read(): List<StudentLearningResponse> = runCatching {
        decode(JSONArray(preferences.getString(RESPONSES, "[]")))
    }.getOrDefault(emptyList())

    private fun encode(values: List<StudentLearningResponse>): JSONArray = JSONArray().also { output ->
        values.forEach { response ->
            output.put(
                JSONObject()
                    .put("content_id", response.contentId)
                    .put("result_id", response.resultId)
                    .put("visit_id", response.visitId)
                    .put("source", response.source.name)
                    .put("evidence_refs", JSONArray(response.evidenceRefs.map { it.value }))
                    .put("stage", response.stage.name)
                    .put("body", response.body)
                    .put("recorded_at", response.recordedAt.toString()),
            )
        }
    }

    private fun decode(values: JSONArray): List<StudentLearningResponse> = buildList {
        for (index in 0 until values.length()) {
            runCatching {
                val value = values.getJSONObject(index)
                StudentLearningResponse(
                    resultId = value.getString("result_id"),
                    contentId = value.getString("content_id"),
                    visitId = value.getString("visit_id"),
                    source = cn.zhixingzhixue.learning.domain.CandidateMediaSource.valueOf(value.getString("source")),
                    evidenceRefs = value.getJSONArray("evidence_refs").let { refs ->
                        List(refs.length()) { refIndex -> cn.zhixingzhixue.learning.domain.LocalEvidenceRef(refs.getString(refIndex)) }
                    },
                    stage = LearningStage.valueOf(value.getString("stage")),
                    body = value.getString("body"),
                    recordedAt = OffsetDateTime.parse(value.getString("recorded_at")),
                )
            }.getOrNull()?.let(::add)
        }
    }

    private companion object {
        private const val PREFERENCES: String = "zhixing_learning_response_journal_v1"
        private const val RESPONSES: String = "responses"
    }
}
