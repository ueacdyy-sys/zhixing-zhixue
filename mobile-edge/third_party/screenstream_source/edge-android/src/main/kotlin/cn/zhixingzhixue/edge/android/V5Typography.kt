package cn.zhixingzhixue.edge.android

import androidx.compose.ui.text.font.FontFamily

/** One explicit family boundary for the V5 product UI. */
internal object V5Typography {
    // Keep the product's approved system-font policy.  Typography changes are
    // a visual-design decision and must not be substituted during UI repair.
    val Family: FontFamily = FontFamily.Default
}
