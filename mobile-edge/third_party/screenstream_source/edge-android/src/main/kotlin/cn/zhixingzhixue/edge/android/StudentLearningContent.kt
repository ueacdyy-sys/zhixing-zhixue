package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.domain.LearningStage
import cn.zhixingzhixue.learning.domain.StudentLearningAction
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import java.time.OffsetDateTime
import kotlinx.coroutines.launch

/** Real PC content package: L1 brief -> L2 exploration -> L3 guided -> L4 independent. */
@Composable
public fun StudentLearningContent(
    store: AndroidPcLearningContentStore,
    paths: AndroidLearningPathStore,
    source: cn.zhixingzhixue.learning.domain.CandidateMediaSource,
    modifier: Modifier = Modifier,
) {
    val allItems by store.observe().collectAsState()
    val items = allItems.filter { it.source == source }
    if (items.isEmpty()) return
    val context = LocalContext.current
    val responseStore = remember { MobileAppServices.learningResponseStore(context) }
    var openedId by rememberSaveable { mutableStateOf<String?>(null) }
    val opened = items.firstOrNull { it.content.contentId == openedId }
    if (opened == null) {
        GlassPanel(modifier = modifier.fillMaxWidth()) {
            Text("可学习的知识内容", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(8.dp))
            Text("以下内容由 PC 对对应连续媒体证据完成分析后回传。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            items.forEach { item ->
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = { openedId = item.content.contentId },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                ) { Text(item.content.conceptTitle, fontFamily = V5Typography.Family) }
            }
        }
    } else {
        StudentLearningDetail(opened, paths, responseStore, onBack = { openedId = null }, modifier)
    }
}

@Composable
private fun StudentLearningDetail(
    item: PcLearningContentItem,
    paths: AndroidLearningPathStore,
    responseStore: AndroidLearningResponseStore,
    onBack: () -> Unit,
    modifier: Modifier,
) {
    val states by paths.observe().collectAsState()
    val responses by responseStore.observe(item.resultId, item.content.contentId).collectAsState(initial = emptyList())
    val context = LocalContext.current
    val responseRecorder = remember { MobileAppServices.learningResponseRecorder(context) }
    val scope = rememberCoroutineScope()
    val stage = states[item.content.contentId]?.stage ?: LearningStage.L0_CANDIDATE
    val content = item.content
    var guidedDraft by rememberSaveable(content.contentId) { mutableStateOf("") }
    var selfDraft by rememberSaveable(content.contentId) { mutableStateOf("") }
    val guidedCount = responses.count { it.stage == LearningStage.L3_GUIDED_PRACTICE }
    val selfCount = responses.count { it.stage == LearningStage.L4_SELF_PRACTICE }

    GlassPanel(modifier = modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(content.conceptTitle, color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.SemiBold)
            val sourceLabel = if (item.source.name == "PHONE_SCREEN") "手机屏幕流" else "眼镜第一视角"
            Text("证据关联：$sourceLabel · ${item.visitId} · ${content.evidenceRefs.size} 条", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            if (stage == LearningStage.L0_CANDIDATE) {
                ActionButton("开始 L1 概念小结") { paths.dispatchContent(content.contentId, StudentLearningAction.OPEN_L1_CONCEPT_BRIEF) }
            }
            if (stage >= LearningStage.L1_CONCEPT_BRIEF) {
                Section("L1 概念小结", content.conceptBrief)
                if (stage == LearningStage.L1_CONCEPT_BRIEF) {
                    ActionButton("自愿进入 L2 深入探究") { paths.dispatchContent(content.contentId, StudentLearningAction.OPEN_L2_EXPLORATION) }
                }
            }
            if (stage >= LearningStage.L2_EXPLORATION) {
                Section("L2 背景与联系", content.background)
                Section("实例解析", content.workedExample)
                Text("可信材料", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
                content.trustedResources.forEach { resource ->
                    Text("• ${resource.publisher}｜${resource.title}", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                }
            }
            if (stage >= LearningStage.L2_EXPLORATION) {
                if (stage == LearningStage.L2_EXPLORATION) {
                    ActionButton("开始 L3 引导练习") { paths.dispatchContent(content.contentId, StudentLearningAction.START_L3_GUIDED_PRACTICE) }
                }
            }
            if (stage >= LearningStage.L3_GUIDED_PRACTICE) {
                Section("L3 引导练习", content.guidedPractice)
                if (stage == LearningStage.L3_GUIDED_PRACTICE) {
                    LearningResponseEditor(
                        value = guidedDraft,
                        onValueChange = { guidedDraft = it },
                        label = "写下本次练习的理由或步骤",
                        savedCount = guidedCount,
                        saveLabel = "保存本次 L3 练习",
                        enabled = guidedDraft.isNotBlank(),
                        onSave = {
                            val body = guidedDraft.trim()
                            scope.launch {
                            responseRecorder.record(
                                    StudentLearningResponse(
                                        resultId = item.resultId,
                                        contentId = content.contentId,
                                        visitId = item.visitId,
                                        source = item.source,
                                        evidenceRefs = content.evidenceRefs,
                                        stage = LearningStage.L3_GUIDED_PRACTICE,
                                        body = body,
                                        recordedAt = OffsetDateTime.now(),
                                    ),
                                )
                                guidedDraft = ""
                            }
                        },
                    )
                }
            }
            if (stage == LearningStage.L3_GUIDED_PRACTICE) {
                ActionButton("自愿进入 L4 自主表达") { paths.dispatchContent(content.contentId, StudentLearningAction.START_L4_SELF_PRACTICE) }
            }
            if (stage >= LearningStage.L4_SELF_PRACTICE) {
                Section("L4 自主表达", content.selfPractice)
                LearningResponseEditor(
                    value = selfDraft,
                    onValueChange = { selfDraft = it },
                    label = "用自己的话记录理解、问题或例子",
                    savedCount = selfCount,
                    saveLabel = "保存本次 L4 表达",
                    enabled = selfDraft.isNotBlank(),
                    onSave = {
                        val body = selfDraft.trim()
                        scope.launch {
                            responseRecorder.record(
                                    StudentLearningResponse(
                                        resultId = item.resultId,
                                        contentId = content.contentId,
                                        visitId = item.visitId,
                                        source = item.source,
                                        evidenceRefs = content.evidenceRefs,
                                        stage = LearningStage.L4_SELF_PRACTICE,
                                        body = body,
                                        recordedAt = OffsetDateTime.now(),
                                    ),
                            )
                            selfDraft = ""
                        }
                    },
                )
            }
            Button(onClick = onBack, colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk)) { Text("返回内容列表", fontFamily = V5Typography.Family) }
        }
    }
}

@Composable
private fun LearningResponseEditor(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    savedCount: Int,
    saveLabel: String,
    enabled: Boolean,
    onSave: () -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label, fontFamily = V5Typography.Family) },
        minLines = 3,
    )
    Text(
        if (savedCount == 0) "仅保存在本机学习记录中，当前不会自动评分或外传。" else "已在本机保存 $savedCount 条本层回应。",
        color = ZhixingVisualTokens.SecondaryInk,
        fontFamily = V5Typography.Family,
    )
    Button(
        onClick = onSave,
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
    ) { Text(saveLabel, fontFamily = V5Typography.Family) }
}

@Composable
private fun Section(title: String, body: String) {
    Text(title, color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
    Text(body, color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
}

@Composable
private fun ActionButton(label: String, onClick: () -> Unit) {
    Button(onClick = onClick, colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White)) {
        Text(label, fontFamily = V5Typography.Family)
    }
}
