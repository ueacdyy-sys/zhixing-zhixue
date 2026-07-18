package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.background
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
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/** Student-facing home. RTSP stays behind the explicit “devices and media” page. */
@Composable
public fun StudentHomeContent(onOpenMediaControl: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val candidates = remember { AndroidCandidateRepository(context.applicationContext) }
    val candidateItems by (session?.let { active -> candidates.observe(active.id) }
        ?: kotlinx.coroutines.flow.flowOf(emptyList())).collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(ZhixingVisualTokens.CanvasTop, ZhixingVisualTokens.CanvasBottom)))
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 24.dp),
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
            CandidatePanel(candidateItems.isEmpty(), candidateItems.firstOrNull()?.ocrExcerpt)
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
private fun CandidatePanel(isEmpty: Boolean, excerpt: String?) {
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
                if (isEmpty) stringResource(R.string.student_candidates_waiting) else stringResource(R.string.student_candidates_ready),
                modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(ZhixingVisualTokens.AccentSoft).padding(horizontal = 10.dp, vertical = 5.dp),
                color = ZhixingVisualTokens.Accent,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium
            )
        }
        Spacer(Modifier.height(12.dp))
        Text(
            if (isEmpty) stringResource(R.string.student_candidates_empty) else excerpt.orEmpty(),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
            style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
        )
    }
}

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
