package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.StudentReceipt
import cn.zhixingzhixue.learning.domain.StudentReceiptAction
import cn.zhixingzhixue.learning.domain.KnowledgeResourceAvailability
import cn.zhixingzhixue.learning.domain.StudentLearningAction
import cn.zhixingzhixue.learning.domain.AgentContextReference
import kotlinx.coroutines.launch

/** Student-facing home. RTSP stays behind the explicit “devices and media” page. */
@Composable
public fun StudentHomeContent(
    focusCandidateCardId: String? = null,
    onAskAgent: (List<AgentContextReference>) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val candidateCards = remember { MobileAppServices.candidateStore(context) }
    val cardItems by candidateCards.observe().collectAsState(initial = emptyList())
    val learningPaths = remember { MobileAppServices.learningPathStore(context) }
    val learningContent = remember { MobileAppServices.learningContentStore(context) }
    val receiptStore = remember { AndroidReceiptStore(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var selectedSource by rememberSaveable { mutableStateOf(CandidateMediaSource.PHONE_SCREEN) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(ZhixingVisualTokens.CanvasTop, ZhixingVisualTokens.CanvasBottom)))
    ) {
        Column(
            modifier = Modifier
                .padding(start = 20.dp, end = 20.dp, top = 62.dp, bottom = 24.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Text(
                stringResource(R.string.student_home_title),
                color = ZhixingVisualTokens.Ink,
                fontFamily = V5Typography.Family,
                fontWeight = FontWeight.SemiBold,
                style = androidx.compose.material3.MaterialTheme.typography.headlineLarge
            )
            Text(
                stringResource(R.string.student_home_subtitle),
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = V5Typography.Family,
                style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
            )
            SessionPanel(
                sessionActive = session != null,
                onOpen = { scope.launch { sessionStore.open() } }
            )
            SourceSelector(selectedSource = selectedSource, onSelect = { selectedSource = it })
            CandidatePanel(
                cards = cardItems.filter { it.source == selectedSource },
                focusCandidateCardId = focusCandidateCardId,
                learningPaths = learningPaths,
                onReceipt = { card, action ->
                    scope.launch {
                        receiptStore.record(
                            StudentReceipt(
                                captureId = null,
                                evidenceCardId = null,
                                candidateCardId = card.id,
                                action = action,
                                recordedAt = java.time.OffsetDateTime.now(),
                            )
                        )
                    }
                },
                onAskAgent = { cards ->
                    onAskAgent(cards.map { card -> card.toAgentContextReference() })
                },
            )
            StudentLearningContent(learningContent, learningPaths, selectedSource)
        }
    }
}

@Composable
private fun SourceSelector(
    selectedSource: CandidateMediaSource,
    onSelect: (CandidateMediaSource) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        SourceButton("手机屏幕流", selectedSource == CandidateMediaSource.PHONE_SCREEN) { onSelect(CandidateMediaSource.PHONE_SCREEN) }
        SourceButton("眼镜第一视角", selectedSource == CandidateMediaSource.GLASSES_FIRST_PERSON) { onSelect(CandidateMediaSource.GLASSES_FIRST_PERSON) }
    }
}

@Composable
private fun SourceButton(label: String, selected: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (selected) ZhixingVisualTokens.Accent else ZhixingVisualTokens.Quiet,
            contentColor = if (selected) androidx.compose.ui.graphics.Color.White else ZhixingVisualTokens.Accent,
        ),
        shape = RoundedCornerShape(15.dp),
    ) { Text(label, fontFamily = V5Typography.Family) }
}

@Composable
private fun SessionPanel(sessionActive: Boolean, onOpen: () -> Unit) {
    GlassPanel(modifier = Modifier.fillMaxWidth(), elevation = 10.dp) {
        Text(
            if (sessionActive) stringResource(R.string.student_session_active) else stringResource(R.string.student_session_open),
            color = ZhixingVisualTokens.Ink,
            fontFamily = V5Typography.Family,
            fontWeight = FontWeight.Medium,
            style = androidx.compose.material3.MaterialTheme.typography.titleLarge
        )
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(if (sessionActive) R.string.student_session_active_detail else R.string.student_session_open_detail),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = V5Typography.Family,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
        if (!sessionActive) {
            Spacer(Modifier.height(18.dp))
            Button(
                onClick = onOpen,
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                shape = RoundedCornerShape(15.dp),
                contentPadding = ButtonDefaults.ContentPadding
            ) { Text(stringResource(R.string.student_session_open), fontFamily = V5Typography.Family) }
        }
    }
}

@Composable
private fun CandidatePanel(
    cards: List<CandidateCard>,
    focusCandidateCardId: String?,
    learningPaths: AndroidLearningPathStore,
    onReceipt: (CandidateCard, StudentReceiptAction) -> Unit,
    onAskAgent: (List<CandidateCard>) -> Unit,
) {
    val latest = cards.lastOrNull { it.id.value == focusCandidateCardId } ?: cards.lastOrNull()
    val pathStates by learningPaths.observe().collectAsState()
    var evidenceExpanded by rememberSaveable(latest?.id?.value) { mutableStateOf(false) }
    var selectionMode by rememberSaveable { mutableStateOf(false) }
    var selectedForAgent by rememberSaveable { mutableStateOf(emptySet<String>()) }
    GlassPanel(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.student_candidates_title),
                color = ZhixingVisualTokens.Ink,
                fontFamily = V5Typography.Family,
                fontWeight = FontWeight.Medium,
                style = androidx.compose.material3.MaterialTheme.typography.titleMedium
            )
            Spacer(Modifier.weight(1f))
            Text(
                if (latest == null) stringResource(R.string.student_candidates_waiting) else stringResource(R.string.student_candidates_ready),
                modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(ZhixingVisualTokens.AccentSoft).padding(horizontal = 10.dp, vertical = 5.dp),
                color = ZhixingVisualTokens.Accent,
                fontFamily = V5Typography.Family,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium
            )
        }
        Spacer(Modifier.height(12.dp))
        Text(
            latest?.displayExcerpt?.take(MAX_EXCERPT_CHARS) ?: stringResource(R.string.student_candidates_empty),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = V5Typography.Family,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
        if (latest != null) {
            Spacer(Modifier.height(14.dp))
            Button(
                onClick = { evidenceExpanded = !evidenceExpanded },
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                shape = RoundedCornerShape(15.dp),
            ) {
                Text(
                    stringResource(if (evidenceExpanded) R.string.student_candidate_collapse_evidence else R.string.student_candidate_view_evidence),
                    fontFamily = V5Typography.Family,
                )
            }
            if (evidenceExpanded) {
                Spacer(Modifier.height(12.dp))
                latest.facts.forEach { fact ->
                    Text(
                        text = "${fact.lane.name} · ${fact.text.take(MAX_FACT_CHARS)}",
                        color = ZhixingVisualTokens.SecondaryInk,
                        fontFamily = V5Typography.Family,
                        style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(6.dp))
                }
                Text(
                    stringResource(R.string.student_candidate_knowledge_pending),
                    color = ZhixingVisualTokens.SecondaryInk,
                    fontFamily = V5Typography.Family,
                    style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
                )
            }
            val stage = pathStates[latest.id.value]?.stage?.name ?: "L0_CANDIDATE"
            Spacer(Modifier.height(10.dp))
            Text(
                text = "当前学习阶梯：" + stage,
                color = ZhixingVisualTokens.Accent,
                fontFamily = V5Typography.Family,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.SAVE) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_save), fontFamily = V5Typography.Family) }
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.WATCH_LATER) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_later), fontFamily = V5Typography.Family) }
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.DISMISS) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_dismiss), fontFamily = V5Typography.Family) }
            }
            Spacer(Modifier.height(8.dp))
            if (latest.isL1Eligible) {
                Button(
                    onClick = {
                        learningPaths.dispatch(
                            latest,
                            StudentLearningAction.OPEN_L1_CONCEPT_BRIEF,
                            KnowledgeResourceAvailability.UNRESOLVED,
                        )
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                    shape = RoundedCornerShape(15.dp),
                ) { Text("自主进入 L1（资源就绪后开启）", fontFamily = V5Typography.Family) }
            } else {
                Text("该第一视角片段已封存，待回家后对齐完整证据再开放学习入口。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            }
            Spacer(Modifier.height(10.dp))
            if (!selectionMode) {
                Button(
                    onClick = { selectionMode = true },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                    shape = RoundedCornerShape(15.dp),
                ) { Text("选择会话问智能体", fontFamily = V5Typography.Family) }
            } else {
                Text("选择后仅转交会话摘要与证据引用；不会改变 L0–L4。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                cards.takeLast(12).reversed().forEach { card ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = card.id.value in selectedForAgent,
                            onCheckedChange = { checked ->
                                selectedForAgent = if (checked) selectedForAgent + card.id.value else selectedForAgent - card.id.value
                            },
                        )
                        Text(card.displayExcerpt.take(72), color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = {
                            selectionMode = false
                            selectedForAgent = emptySet()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk),
                    ) { Text("取消", fontFamily = V5Typography.Family) }
                    Button(
                        onClick = {
                            onAskAgent(cards.filter { it.id.value in selectedForAgent })
                            selectionMode = false
                            selectedForAgent = emptySet()
                        },
                        enabled = selectedForAgent.isNotEmpty(),
                        colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                    ) { Text("问智能体", fontFamily = V5Typography.Family) }
                }
            }
        }
    }
}

private fun CandidateCard.toAgentContextReference(): AgentContextReference = AgentContextReference(
    id = id.value,
    title = if (source == CandidateMediaSource.PHONE_SCREEN) "手机屏幕流会话" else "眼镜第一视角会话",
    summary = displayExcerpt,
    source = source,
    visitId = visitId,
    evidenceRefs = evidenceRefs,
)

private const val MAX_EXCERPT_CHARS: Int = 180
private const val MAX_FACT_CHARS: Int = 120

@Composable
public fun StudentConnectionContent(
    onOpenMediaControl: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val linkStore = remember { MobileAppServices.pcLinkStore(context) }
    val deliveryClient = remember { MobileAppServices.pcDeliveryClient(context) }
    var activeLink by remember { mutableStateOf(linkStore.read()) }
    var pcAddress by rememberSaveable { mutableStateOf(activeLink?.baseUrl ?: "") }
    var pairingCode by rememberSaveable { mutableStateOf("") }
    var syncMessage by rememberSaveable { mutableStateOf("") }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(ZhixingVisualTokens.CanvasTop, ZhixingVisualTokens.CanvasBottom)))
            .verticalScroll(rememberScrollState())
            .padding(start = 20.dp, end = 20.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("连接", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.SemiBold, style = androidx.compose.material3.MaterialTheme.typography.headlineLarge)
        Text("管理手机、PC 与后续可接入设备的数据边界。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
    GlassPanel(modifier = Modifier.fillMaxWidth()) {
        Text(
            stringResource(R.string.student_devices_title),
            color = ZhixingVisualTokens.Ink,
            fontFamily = V5Typography.Family,
            fontWeight = FontWeight.Medium,
            style = androidx.compose.material3.MaterialTheme.typography.titleMedium
        )
        Spacer(Modifier.height(8.dp))
        Text(
            if (activeLink == null) stringResource(R.string.student_devices_value) else stringResource(R.string.student_devices_paired),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = V5Typography.Family,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
        if (activeLink == null) {
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = pcAddress,
                onValueChange = { pcAddress = it },
                label = { Text(stringResource(R.string.student_pair_pc_address)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = pairingCode,
                onValueChange = { pairingCode = it },
                label = { Text(stringResource(R.string.student_pair_code)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            Button(
                onClick = {
                    scope.launch {
                        runCatching { deliveryClient.pair(pcAddress, pairingCode) }
                            .onSuccess {
                                activeLink = it
                                PcSyncForegroundService.start(context)
                                pairingCode = ""
                                syncMessage = "PC 已配对，后台同步已开启"
                            }
                            .onFailure { syncMessage = "配对失败，请检查地址与配对码" }
                    }
                },
                enabled = pcAddress.isNotBlank() && pairingCode.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                shape = RoundedCornerShape(15.dp),
            ) { Text(stringResource(R.string.student_pair_pc), fontFamily = V5Typography.Family) }
        } else {
            Spacer(Modifier.height(10.dp))
            Text(
                syncMessage.ifBlank { stringResource(R.string.student_sync_waiting) },
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = V5Typography.Family,
                style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
            )
            Button(
                onClick = {
                    scope.launch {
                        PcSyncForegroundService.stop(context)
                        deliveryClient.unpair()
                        activeLink = null
                        syncMessage = ""
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk),
                shape = RoundedCornerShape(15.dp),
            ) { Text(stringResource(R.string.student_unpair_pc), fontFamily = V5Typography.Family) }
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onOpenMediaControl,
            modifier = Modifier.wrapContentWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
            shape = RoundedCornerShape(15.dp)
        ) { Text(stringResource(R.string.student_media_control), fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium) }
    }
        GlassPanel(modifier = Modifier.fillMaxWidth()) {
            Text("外出设备链", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(7.dp))
            DeviceTransportRow("手机", "当前应用", "本地保存候选卡、学习回应、知识图谱与设备时间轴")
            DeviceTransportRow("眼镜", "尚未接入", "BLE 用于控制与低频状态；高带宽第一视角视频后续通过 Wi-Fi Direct 存入手机")
            DeviceTransportRow("手表", "尚未接入", "BLE 同步状态流至手机；手机再与 PC 对齐，不要求手表靠近 PC")
            Spacer(Modifier.height(4.dp))
            Text("未接入设备不会伪造为已连接；当前 PC 配对只同步明确允许同步的候选、学习内容和图谱事件。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family, style = androidx.compose.material3.MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun DeviceTransportRow(name: String, status: String, detail: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(name, color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
            Text(status, color = if (status == "当前应用") ZhixingVisualTokens.Accent else ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        }
        Text(detail, color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family, style = androidx.compose.material3.MaterialTheme.typography.bodySmall)
    }
}
