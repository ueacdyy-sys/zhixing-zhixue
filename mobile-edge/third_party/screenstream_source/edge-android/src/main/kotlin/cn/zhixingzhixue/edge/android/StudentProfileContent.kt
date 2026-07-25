package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** Learning-analysis workspace: evidence index and editable all-session knowledge vault. */
@Composable
public fun StudentProfileContent(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val vault = remember { MobileAppServices.knowledgeVault(context) }
    val profile by vault.observeProfile().collectAsState(initial = emptyList())
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(start = 20.dp, end = 20.dp, top = 62.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("学习分析", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.SemiBold)
        Text("查看知识来源、学习记录与学生维护的知识脉络。统计不推断人格、能力或医疗结论。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        GlassPanel(modifier = Modifier) {
            Text("候选主题索引", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
            if (profile.isEmpty()) {
                Text("等待来自完整证据分析的候选主题。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            } else {
                profile.take(12).forEach { entry ->
                    Text("${entry.subjectTag} · ${entry.topic} · 候选证据", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                }
            }
        }
        StudentLearningAnalytics(profile)
        StudentKnowledgeGraphContent(vault)
    }
}
