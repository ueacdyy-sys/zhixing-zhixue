package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.application.LearningResponseEligibilityPort
import cn.zhixingzhixue.learning.domain.StudentLearningResponse

/** Outer adapter for the two local facts an L3/L4 writing record must satisfy. */
public class AndroidLearningResponseEligibility(
    private val contentStore: AndroidPcLearningContentStore,
    private val pathStore: AndroidLearningPathStore,
) : LearningResponseEligibilityPort {
    override suspend fun canRecord(response: StudentLearningResponse): Boolean {
        val currentStage = pathStore.observe().value[response.contentId]?.stage ?: return false
        if (currentStage != response.stage) return false
        return contentStore.observe().value.any { item ->
            item.resultId == response.resultId &&
                item.content.contentId == response.contentId &&
                item.visitId == response.visitId &&
                item.source == response.source &&
                item.content.evidenceRefs == response.evidenceRefs
        }
    }
}
