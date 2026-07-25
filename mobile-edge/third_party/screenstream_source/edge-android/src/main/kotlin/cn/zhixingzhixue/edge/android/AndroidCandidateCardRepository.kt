package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.CandidateCardRepository
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateCardClassification
import cn.zhixingzhixue.learning.domain.CandidateCardGate
import cn.zhixingzhixue.learning.domain.CandidateCardId
import cn.zhixingzhixue.learning.domain.CandidateEvidenceFact
import cn.zhixingzhixue.learning.domain.CandidateEvidenceLane
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONArray
import org.json.JSONObject

/** Local-first store for complete, mobile-readable candidate evidence cards. */
public class AndroidCandidateCardRepository(context: Context) : CandidateCardRepository {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val cards = MutableStateFlow(readAll())

    override suspend fun upsert(card: CandidateCard) {
        val updated = cards.value.filterNot { it.id == card.id } + card
        preferences.edit().putString(CARDS, encode(updated).toString()).apply()
        cards.value = updated
    }

    override fun observe(): Flow<List<CandidateCard>> = cards

    /** Snapshot for an explicit user-initiated local export. */
    public fun snapshot(): List<CandidateCard> = cards.value

    private fun readAll(): List<CandidateCard> = runCatching {
        decode(JSONArray(preferences.getString(CARDS, "[]")))
    }.getOrDefault(emptyList())

    private fun encode(items: List<CandidateCard>): JSONArray = JSONArray().also { array ->
        items.forEach { card ->
            array.put(
                JSONObject()
                    .put("id", card.id.value)
                    .put("captureId", card.captureId.value)
                    .put("visitId", card.visitId)
                    .put("startPtsNs", card.startPtsNs)
                    .put("endPtsNs", card.endPtsNs)
                    .put("refs", JSONArray(card.evidenceRefs.map { ref -> ref.value }))
                    .put("facts", JSONArray(card.facts.map { fact -> JSONObject().put("lane", fact.lane.name).put("text", fact.text) }))
                    .put("displayExcerpt", card.displayExcerpt)
                    .put("classification", card.classification.name)
                    .put("isL1Eligible", card.isL1Eligible)
                    .put("source", card.source.name)
            )
        }
    }

    private fun decode(array: JSONArray): List<CandidateCard> = buildList {
        for (index in 0 until array.length()) {
            val item = array.getJSONObject(index)
            val facts = item.getJSONArray("facts").let { values ->
                List(values.length()) { factIndex ->
                    values.getJSONObject(factIndex).let { fact ->
                        CandidateEvidenceFact(CandidateEvidenceLane.valueOf(fact.getString("lane")), fact.getString("text"))
                    }
                }
            }
            val refs = item.getJSONArray("refs").let { values ->
                List(values.length()) { refIndex -> LocalEvidenceRef(values.getString(refIndex)) }
            }
            val card = CandidateCardGate.fromTrimodalEvidence(
                id = CandidateCardId(item.getString("id")),
                captureId = CaptureId(item.getString("captureId")),
                visitId = item.getString("visitId"),
                startPtsNs = item.getLong("startPtsNs"),
                endPtsNs = item.getLong("endPtsNs"),
                evidenceRefs = refs,
                facts = facts,
                displayExcerpt = item.getString("displayExcerpt"),
                source = item.optString("source", CandidateMediaSource.PHONE_SCREEN.name)
                    .let { CandidateMediaSource.valueOf(it) },
                isL1Eligible = item.optBoolean("isL1Eligible", false),
            )
            if (item.getString("classification") == CandidateCardClassification.CANDIDATE_ONLY.name && card != null) {
                add(card)
            }
        }
    }

    private companion object {
        private const val PREFERENCES = "zhixing_mobile_learning"
        private const val CARDS = "candidate_cards_v1"
    }
}
