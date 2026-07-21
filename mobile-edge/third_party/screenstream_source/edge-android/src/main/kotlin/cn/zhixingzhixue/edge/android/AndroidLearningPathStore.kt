package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.KnowledgeResourceAvailability
import cn.zhixingzhixue.learning.domain.LearningPathReducer
import cn.zhixingzhixue.learning.domain.LearningPathState
import cn.zhixingzhixue.learning.domain.LearningStage
import cn.zhixingzhixue.learning.domain.StudentLearningAction
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** Per-candidate voluntary L0-L4 ledger. No dwell time or notification count enters it. */
public class AndroidLearningPathStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val paths = MutableStateFlow(readAll())

    public fun observe(): StateFlow<Map<String, LearningPathState>> = paths

    public fun stateFor(cardId: String): LearningPathState =
        paths.value[cardId] ?: LearningPathState(LearningStage.L0_CANDIDATE)

    public fun dispatch(
        card: CandidateCard,
        action: StudentLearningAction,
        resourceAvailability: KnowledgeResourceAvailability,
    ): Boolean {
        val transition = LearningPathReducer.reduce(
            current = stateFor(card.id.value),
            action = action,
            hasCompleteCandidateEvidence = card.isL1Eligible,
            resourceAvailability = resourceAvailability,
        )
        if (!transition.accepted) return false
        val updated = paths.value + (card.id.value to transition.state)
        preferences.edit().putString(card.id.value, transition.state.stage.name).apply()
        paths.value = updated
        return true
    }

    private fun readAll(): Map<String, LearningPathState> = preferences.all.mapNotNull { (key, value) ->
        val stage = (value as? String)?.let { runCatching { LearningStage.valueOf(it) }.getOrNull() } ?: return@mapNotNull null
        key to LearningPathState(stage)
    }.toMap()

    private companion object {
        private const val PREFERENCES: String = "zhixing_learning_paths_v1"
    }
}
