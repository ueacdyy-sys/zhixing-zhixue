package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Formal inbox boundary for PC-to-phone results. Transport is intentionally
 * separate: ADB diagnostics cannot call this product path.
 */
public class AndroidPcResultInbox(
    private val knowledgeVault: AndroidKnowledgeGraphRepository,
    private val learningContent: AndroidPcLearningContentStore,
) {
    public suspend fun accept(raw: String): KnowledgeGraphProjection = withContext(Dispatchers.Default) {
        val result = PcKnowledgeResultCodec.decode(raw)
        val projection = knowledgeVault.apply(result)
        learningContent.accept(result)
        projection
    }
}
