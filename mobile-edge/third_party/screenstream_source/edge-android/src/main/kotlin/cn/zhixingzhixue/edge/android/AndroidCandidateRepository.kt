package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.CandidateRepository
import cn.zhixingzhixue.learning.domain.AudioCompleteness
import cn.zhixingzhixue.learning.domain.CandidateId
import cn.zhixingzhixue.learning.domain.CandidateStatus
import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.EvidenceWindow
import cn.zhixingzhixue.learning.domain.KnowledgePointCandidate
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.MobileEvidenceSource
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.TimeQuality
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime

/** Local-first candidate cache. It stores only structured candidate metadata and local references. */
public class AndroidCandidateRepository(context: Context) : CandidateRepository {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val candidates = MutableStateFlow(readAll())

    override suspend fun upsert(candidate: KnowledgePointCandidate) {
        val updated = candidates.value.filterNot { it.id == candidate.id } + candidate
        preferences.edit().putString(CANDIDATES, encode(updated).toString()).apply()
        candidates.value = updated
    }

    override fun observe(sessionId: MobileSessionId): Flow<List<KnowledgePointCandidate>> =
        candidates.map { all -> all.filter { it.sessionId == sessionId } }

    private fun readAll(): List<KnowledgePointCandidate> = runCatching {
        decode(JSONArray(preferences.getString(CANDIDATES, "[]")))
    }.getOrDefault(emptyList())

    private fun encode(items: List<KnowledgePointCandidate>): JSONArray = JSONArray().also { array ->
        items.forEach { item ->
            array.put(
                JSONObject()
                    .put("id", item.id.value)
                    .put("sessionId", item.sessionId.value)
                    .put("captureId", item.captureId.value)
                    .put("status", item.status.name)
                    .put("source", item.source.name)
                    .put("startedAt", item.evidenceWindow.startedAt.toString())
                    .put("endedAt", item.evidenceWindow.endedAt.toString())
                    .put("audio", item.evidenceWindow.audioCompleteness.name)
                    .put("time", item.evidenceWindow.timeQuality.name)
                    .put("refs", JSONArray(item.evidenceRefs.map { ref -> ref.value }))
                    .put("ocr", item.ocrExcerpt)
            )
        }
    }

    private fun decode(array: JSONArray): List<KnowledgePointCandidate> = buildList {
        for (index in 0 until array.length()) {
            val item = array.getJSONObject(index)
            val refs = item.getJSONArray("refs").let { values ->
                List(values.length()) { refIndex -> LocalEvidenceRef(values.getString(refIndex)) }
            }
            add(
                KnowledgePointCandidate(
                    id = CandidateId(item.getString("id")),
                    sessionId = MobileSessionId(item.getString("sessionId")),
                    captureId = CaptureId(item.getString("captureId")),
                    status = CandidateStatus.valueOf(item.getString("status")),
                    source = MobileEvidenceSource.valueOf(item.getString("source")),
                    evidenceWindow = EvidenceWindow(
                        startedAt = OffsetDateTime.parse(item.getString("startedAt")),
                        endedAt = OffsetDateTime.parse(item.getString("endedAt")),
                        audioCompleteness = AudioCompleteness.valueOf(item.getString("audio")),
                        timeQuality = TimeQuality.valueOf(item.getString("time"))
                    ),
                    evidenceRefs = refs,
                    ocrExcerpt = item.optString("ocr").takeIf { value -> value.isNotBlank() }
                )
            )
        }
    }

    private companion object {
        private const val PREFERENCES = "zhixing_mobile_learning"
        private const val CANDIDATES = "candidates_v1"
    }
}
