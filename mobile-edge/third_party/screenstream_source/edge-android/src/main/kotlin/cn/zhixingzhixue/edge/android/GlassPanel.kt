package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
internal fun GlassPanel(
    modifier: Modifier = Modifier,
    elevation: Dp = 0.dp,
    contentPadding: PaddingValues = PaddingValues(14.dp),
    content: @Composable ColumnScope.() -> Unit
) {
    val shape = RoundedCornerShape(14.dp)
    Surface(
        modifier = modifier.shadow(elevation, shape, clip = false),
        shape = shape,
        color = ZhixingVisualTokens.Glass,
        border = BorderStroke(1.dp, ZhixingVisualTokens.GlassBorder),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp
    ) {
        androidx.compose.foundation.layout.Column(
            modifier = Modifier.padding(contentPadding),
            content = content
        )
    }
}
