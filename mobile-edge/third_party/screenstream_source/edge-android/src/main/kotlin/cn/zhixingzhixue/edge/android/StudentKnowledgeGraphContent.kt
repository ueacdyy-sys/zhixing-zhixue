package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.application.KnowledgeGraphRepository
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Phone-side, evidence-linked knowledge vault inspired by graph note-taking. */
@Composable
public fun StudentKnowledgeGraphContent(
    repository: KnowledgeGraphRepository,
    modifier: Modifier = Modifier,
) {
    val snapshot by repository.observeGraph().collectAsState(initial = KnowledgeGraphSnapshot.empty())
    val profile by repository.observeProfile().collectAsState(initial = emptyList())

    GlassPanel(modifier = modifier.fillMaxWidth()) {
        Text(
            text = stringResource(R.string.student_graph_title),
            color = ZhixingVisualTokens.Ink,
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Medium,
            style = androidx.compose.material3.MaterialTheme.typography.titleMedium,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = stringResource(R.string.student_graph_detail),
            color = ZhixingVisualTokens.SecondaryInk,
            fontFamily = FontFamily.SansSerif,
            style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
        )
        if (snapshot.nodes.isEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text(
                text = stringResource(R.string.student_graph_empty),
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.bodyMedium,
            )
            return@GlassPanel
        }

        Spacer(Modifier.height(14.dp))
        KnowledgeGraphCanvas(snapshot)
        Spacer(Modifier.height(12.dp))
        snapshot.nodes.forEach { node ->
            GraphNodeRow(node)
            Spacer(Modifier.height(6.dp))
        }
        if (profile.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = stringResource(R.string.student_graph_profile_count, profile.size),
                color = ZhixingVisualTokens.Accent,
                fontFamily = FontFamily.SansSerif,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun KnowledgeGraphCanvas(snapshot: KnowledgeGraphSnapshot) {
    val nodes = snapshot.nodes.take(MAX_VISIBLE_GRAPH_NODES)
    Canvas(
        modifier = Modifier
            .fillMaxWidth()
            .height(190.dp),
    ) {
        val center = Offset(size.width / 2f, size.height / 2f)
        val radius = minOf(size.width, size.height) * 0.33f
        val positions = nodes.mapIndexed { index, _ ->
            val angle = (2.0 * PI * index / nodes.size) - PI / 2.0
            Offset(
                x = center.x + (radius * cos(angle)).toFloat(),
                y = center.y + (radius * sin(angle)).toFloat(),
            )
        }
        snapshot.edges.forEach { edge ->
            val fromIndex = nodes.indexOfFirst { it.id == edge.from }
            val toIndex = nodes.indexOfFirst { it.id == edge.to }
            if (fromIndex >= 0 && toIndex >= 0) {
                drawLine(
                    color = ZhixingVisualTokens.Accent.copy(alpha = 0.38f),
                    start = positions[fromIndex],
                    end = positions[toIndex],
                    strokeWidth = 2.dp.toPx(),
                )
            }
        }
        positions.forEachIndexed { index, position ->
            drawCircle(
                color = if (nodes[index].type.name == "MEDIA_EVIDENCE") {
                    ZhixingVisualTokens.Accent
                } else {
                    ZhixingVisualTokens.AccentSoft
                },
                radius = 18.dp.toPx(),
                center = position,
            )
            drawCircle(
                color = ZhixingVisualTokens.Accent,
                radius = 18.dp.toPx(),
                center = position,
                style = Stroke(width = 1.dp.toPx()),
            )
        }
    }
}

@Composable
private fun GraphNodeRow(node: KnowledgeGraphNode) {
    Text(
        text = "• " + node.label + " · " + node.type.name,
        modifier = Modifier.padding(horizontal = 2.dp),
        color = ZhixingVisualTokens.SecondaryInk,
        fontFamily = FontFamily.SansSerif,
        style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
    )
}

private const val MAX_VISIBLE_GRAPH_NODES: Int = 12
