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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
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
import cn.zhixingzhixue.learning.domain.StudentReceipt
import cn.zhixingzhixue.learning.domain.StudentReceiptAction
import cn.zhixingzhixue.learning.domain.KnowledgeResourceAvailability
import cn.zhixingzhixue.learning.domain.StudentLearningAction
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/** Student-facing home. RTSP stays behind the explicit “devices and media” page. */
@Composable
public fun StudentHomeContent(
    onOpenMediaControl: () -> Unit,
    focusCandidateCardId: String? = null,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val candidateCards = remember { MobileAppServices.candidateStore(context) }
    val cardItems by candidateCards.observe().collectAsState(initial = emptyList())
    val knowledgeVault = remember { MobileAppServices.knowledgeVault(context) }
    val learningPaths = remember { MobileAppServices.learningPathStore(context) }
    val receiptStore = remember { AndroidReceiptStore(context.applicationContext) }
    val scope = rememberCoroutineScope()

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(ZhixingVisualTokens.CanvasTop, ZhixingVisualTokens.CanvasBottom)))
    ) {
        Column(
            modifier = Modifier
                .padding(horizontal = 20.dp, vertical = 24.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Text(
                stringResource(R.string.student_home_title),
                color = ZhixingVisualTokens.Ink,
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.SemiBold,
                style = androidx.compose.material3.MaterialTheme.typography.headlineLarge
            )
            Text(
                stringResource(R.string.student_home_subtitle),
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
            )
            SessionPanel(
                sessionActive = session != null,
                onOpen = { scope.launch { sessionStore.open() } }
            )
            CandidatePanel(
                cards = cardItems,
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
            )
            StudentKnowledgeGraphContent(knowledgeVault)
            DevicePanel(onOpenMediaControl, knowledgeVault)
        }
    }
}

@Composable
private fun SessionPanel(sessionActive: Boolean, onOpen: () -> Unit) {
    GlassPanel(modifier = Modifier.fillMaxWidth(), elevation = 10.dp) {
        Text(
            if (sessionActive) stringResource(R.string.student_session_active) else stringResource(R.string.student_session_open),
            color = ZhixingVisualTokens.Ink,
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Medium,
            style = androidx.compose.material3.MaterialTheme.typography.titleLarge
        )
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(if (sessionActive) R.string.student_session_active_detail else R.string.student_session_open_detail),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
        if (!sessionActive) {
            Spacer(Modifier.height(18.dp))
            Button(
                onClick = onOpen,
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                shape = RoundedCornerShape(15.dp),
                contentPadding = ButtonDefaults.ContentPadding
            ) { Text(stringResource(R.string.student_session_open), fontFamily = FontFamily.SansSerif) }
        }
    }
}

@Composable
private fun CandidatePanel(
    cards: List<CandidateCard>,
    focusCandidateCardId: String?,
    learningPaths: AndroidLearningPathStore,
    onReceipt: (CandidateCard, StudentReceiptAction) -> Unit,
) {
    val latest = cards.lastOrNull { it.id.value == focusCandidateCardId } ?: cards.lastOrNull()
    val pathStates by learningPaths.observe().collectAsState()
    var evidenceExpanded by rememberSaveable(latest?.id?.value) { mutableStateOf(false) }
    GlassPanel(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.student_candidates_title),
                color = ZhixingVisualTokens.Ink,
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Medium,
                style = androidx.compose.material3.MaterialTheme.typography.titleMedium
            )
            Spacer(Modifier.weight(1f))
            Text(
                if (latest == null) stringResource(R.string.student_candidates_waiting) else stringResource(R.string.student_candidates_ready),
                modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(ZhixingVisualTokens.AccentSoft).padding(horizontal = 10.dp, vertical = 5.dp),
                color = ZhixingVisualTokens.Accent,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium
            )
        }
        Spacer(Modifier.height(12.dp))
        Text(
            latest?.displayExcerpt?.take(MAX_EXCERPT_CHARS) ?: stringResource(R.string.student_candidates_empty),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
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
                    fontFamily = FontFamily.SansSerif,
                )
            }
            if (evidenceExpanded) {
                Spacer(Modifier.height(12.dp))
                latest.facts.forEach { fact ->
                    Text(
                        text = "${fact.lane.name} · ${fact.text.take(MAX_FACT_CHARS)}",
                        color = ZhixingVisualTokens.SecondaryInk,
                        fontFamily = FontFamily.SansSerif,
                        style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(6.dp))
                }
                Text(
                    stringResource(R.string.student_candidate_knowledge_pending),
                    color = ZhixingVisualTokens.SecondaryInk,
                    fontFamily = FontFamily.SansSerif,
                    style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
                )
            }
            val stage = pathStates[latest.id.value]?.stage?.name ?: "L0_CANDIDATE"
            Spacer(Modifier.height(10.dp))
            Text(
                text = "当前学习阶梯：" + stage,
                color = ZhixingVisualTokens.Accent,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.SAVE) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_save), fontFamily = FontFamily.SansSerif) }
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.WATCH_LATER) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_later), fontFamily = FontFamily.SansSerif) }
                Button(
                    onClick = { onReceipt(latest, StudentReceiptAction.DISMISS) },
                    colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk),
                    shape = RoundedCornerShape(15.dp),
                ) { Text(stringResource(R.string.student_candidate_dismiss), fontFamily = FontFamily.SansSerif) }
            }
            Spacer(Modifier.height(8.dp))
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
            ) { Text("自主进入 L1（资源就绪后开启）", fontFamily = FontFamily.SansSerif) }
        }
    }
}

private const val MAX_EXCERPT_CHARS: Int = 180
private const val MAX_FACT_CHARS: Int = 120

@Composable
private fun DevicePanel(
    onOpenMediaControl: () -> Unit,
    knowledgeVault: AndroidKnowledgeGraphRepository,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val linkStore = remember { MobileAppServices.pcLinkStore(context) }
    val deliveryClient = remember { MobileAppServices.pcDeliveryClient(context) }
    var activeLink by remember { mutableStateOf(linkStore.read()) }
    var pcAddress by rememberSaveable { mutableStateOf(activeLink?.baseUrl ?: "") }
    var pairingCode by rememberSaveable { mutableStateOf("") }
    var syncMessage by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(activeLink?.deviceId) {
        while (isActive && activeLink != null) {
            runCatching { deliveryClient.synchronizeOnce() }
                .onSuccess { count -> if (count > 0) syncMessage = "已同步 " + count + " 条 PC 分析结果" }
                .onFailure { syncMessage = "PC 同步等待重试" }
            delay(5_000)
        }
    }
    GlassPanel(modifier = Modifier.fillMaxWidth()) {
        Text(
            stringResource(R.string.student_devices_title),
            color = ZhixingVisualTokens.Ink,
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Medium,
            style = androidx.compose.material3.MaterialTheme.typography.titleMedium
        )
        Spacer(Modifier.height(8.dp))
        Text(
            if (activeLink == null) stringResource(R.string.student_devices_value) else stringResource(R.string.student_devices_paired),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
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
                                pairingCode = ""
                                syncMessage = "PC 已配对，正在接收分析结果"
                            }
                            .onFailure { syncMessage = "配对失败，请检查地址与配对码" }
                    }
                },
                enabled = pcAddress.isNotBlank() && pairingCode.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = androidx.compose.ui.graphics.Color.White),
                shape = RoundedCornerShape(15.dp),
            ) { Text(stringResource(R.string.student_pair_pc), fontFamily = FontFamily.SansSerif) }
        } else {
            Spacer(Modifier.height(10.dp))
            Text(
                syncMessage.ifBlank { stringResource(R.string.student_sync_waiting) },
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
            )
            Button(
                onClick = {
                    linkStore.clear()
                    activeLink = null
                    syncMessage = ""
                },
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.SecondaryInk),
                shape = RoundedCornerShape(15.dp),
            ) { Text(stringResource(R.string.student_unpair_pc), fontFamily = FontFamily.SansSerif) }
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onOpenMediaControl,
            modifier = Modifier.wrapContentWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
            shape = RoundedCornerShape(15.dp)
        ) { Text(stringResource(R.string.student_media_control), fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium) }
    }
}
