package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.domain.MobileProfileUpdate
import kotlin.math.max

private enum class LearningChart(val label: String) {
    VENN("韦恩图"), SET("集合图"), SCATTER("散点图"), PIE("饼状图"), BAR("柱状图"), LINE("折线图"),
}

/** Statistical views use only confirmed knowledge-source records, never personality or ability labels. */
@Composable
internal fun StudentLearningAnalytics(profile: List<MobileProfileUpdate>) {
    var chart by rememberSaveable { mutableStateOf(LearningChart.BAR) }
    GlassPanel(modifier = Modifier.fillMaxWidth()) {
        Text("学习分析", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
        Text("仅统计知识主题、来源证据与记录时间；不推断人格或能力。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            LearningChart.entries.forEach { item ->
                TextButton(onClick = { chart = item }) {
                    Text(item.label, color = if (chart == item) ZhixingVisualTokens.Accent else ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                }
            }
        }
        if (profile.isEmpty()) {
            Text("尚无可统计的完整知识来源记录。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        } else {
            LearningAnalyticsCanvas(chart, profile)
        }
    }
}

@Composable
private fun LearningAnalyticsCanvas(chart: LearningChart, profile: List<MobileProfileUpdate>) {
    val subjectCounts = profile.groupingBy { it.subjectTag }.eachCount().entries.sortedByDescending { it.value }.take(4)
    val topicCounts = profile.groupingBy { it.topic }.eachCount().entries.sortedByDescending { it.value }.take(4)
    Column {
        Canvas(modifier = Modifier.fillMaxWidth().height(190.dp).padding(top = 10.dp)) {
            val blue = ZhixingVisualTokens.Accent
            val green = Color(0xFF4A9A72)
            val amber = Color(0xFFE3A536)
            val width = size.width
            val height = size.height
            when (chart) {
                LearningChart.BAR -> {
                    val values = subjectCounts.ifEmpty { topicCounts }
                    val maxCount = max(1, values.maxOfOrNull { it.value } ?: 1)
                    val slot = width / values.size.coerceAtLeast(1)
                    values.forEachIndexed { index, entry ->
                        val barHeight = height * 0.72f * entry.value / maxCount
                        drawRoundRect(blue, topLeft = Offset(slot * index + slot * .2f, height - barHeight - 18f), size = androidx.compose.ui.geometry.Size(slot * .6f, barHeight), cornerRadius = androidx.compose.ui.geometry.CornerRadius(12f, 12f))
                    }
                }
                LearningChart.LINE -> {
                    val points = profile.sortedBy { it.updatedAt }.takeLast(8).mapIndexed { index, _ -> Offset(width * (index + 1f) / 9f, height * (0.30f + (index % 3) * .18f)) }
                    points.zipWithNext().forEach { (from, to) -> drawLine(blue, from, to, strokeWidth = 5f) }
                    points.forEach { drawCircle(blue, 7f, it) }
                }
                LearningChart.SCATTER -> {
                    profile.take(18).forEachIndexed { index, entry ->
                        val x = width * ((index % 6) + 1f) / 7f
                        val y = height * ((entry.topic.length % 5) + 1f) / 6f
                        drawCircle(if (index % 2 == 0) blue else green, 9f, Offset(x, y))
                    }
                }
                LearningChart.PIE -> {
                    val values = subjectCounts.ifEmpty { topicCounts }
                    val total = values.sumOf { it.value }.coerceAtLeast(1)
                    var start = -90f
                    val colors = listOf(blue, green, amber, Color(0xFF8C9AAF))
                    values.forEachIndexed { index, entry ->
                        val sweep = entry.value * 360f / total
                        drawArc(colors[index % colors.size], start, sweep, useCenter = true, topLeft = Offset(width * .22f, height * .05f), size = androidx.compose.ui.geometry.Size(width * .56f, height * .9f))
                        start += sweep
                    }
                    drawCircle(ZhixingVisualTokens.Glass, minOf(width, height) * .18f, Offset(width / 2f, height / 2f))
                }
                LearningChart.VENN -> {
                    drawCircle(blue.copy(alpha = .24f), height * .28f, Offset(width * .40f, height * .45f), style = Stroke(3f))
                    drawCircle(green.copy(alpha = .24f), height * .28f, Offset(width * .60f, height * .45f), style = Stroke(3f))
                    drawCircle(amber.copy(alpha = .24f), height * .28f, Offset(width * .50f, height * .62f), style = Stroke(3f))
                }
                LearningChart.SET -> {
                    drawRoundRect(blue.copy(alpha = .5f), topLeft = Offset(width * .08f, height * .15f), size = androidx.compose.ui.geometry.Size(width * .54f, height * .58f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(18f, 18f), style = Stroke(4f))
                    drawRoundRect(green.copy(alpha = .5f), topLeft = Offset(width * .39f, height * .31f), size = androidx.compose.ui.geometry.Size(width * .53f, height * .54f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(18f, 18f), style = Stroke(4f))
                }
            }
        }
        val labels = when (chart) {
            LearningChart.BAR, LearningChart.PIE -> subjectCounts.ifEmpty { topicCounts }.joinToString(" · ") { "${it.key} ${it.value}" }
            LearningChart.LINE -> "按知识记录时间排序"
            LearningChart.SCATTER -> "主题分布，不代表能力评分"
            LearningChart.VENN -> "主题、来源与学习回应的可交叉查看范围"
            LearningChart.SET -> "同一证据记录可归入多个知识集合"
        }
        Text(labels, color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
    }
}
