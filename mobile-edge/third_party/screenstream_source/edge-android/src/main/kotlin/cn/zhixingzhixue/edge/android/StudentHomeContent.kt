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
import cn.zhixingzhixue.learning.domain.StudentReceipt
import cn.zhixingzhixue.learning.domain.StudentReceiptAction
import kotlinx.coroutines.launch

/** Student-facing home. RTSP stays behind the explicit “devices and media” page. */
@Composable
public fun StudentHomeContent(onOpenMediaControl: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val candidateCards = remember { AndroidCandidateCardRepository(context.applicationContext) }
    val cardItems by candidateCards.observe().collectAsState(initial = emptyList())
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
                onReceipt = { card, action ->
                    scope.launch {
                        receiptStore.record(
                            StudentReceipt(
                                captureId = card.captureId,
                                evidenceCardId = null,
                                action = action,
                                recordedAt = java.time.OffsetDateTime.now(),
                            )
                        )
                    }
                },
            )
            StudentKnowledgeGraphContent()
            DevicePanel(onOpenMediaControl)
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
    onReceipt: (CandidateCard, StudentReceiptAction) -> Unit,
) {
    val latest = cards.lastOrNull()
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
        }
    }
}

private const val MAX_EXCERPT_CHARS: Int = 180
private const val MAX_FACT_CHARS: Int = 120

@Composable
private fun DevicePanel(onOpenMediaControl: () -> Unit) {
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
            stringResource(R.string.student_devices_value),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onOpenMediaControl,
            modifier = Modifier.wrapContentWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
            shape = RoundedCornerShape(15.dp)
        ) { Text(stringResource(R.string.student_media_control), fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium) }
    }
}
