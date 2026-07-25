package info.dvkr.screenstream

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import cn.zhixingzhixue.edge.android.V5NativeApp
import cn.zhixingzhixue.edge.android.MobileAppServices
import info.dvkr.screenstream.ui.theme.ScreenStreamTheme
import info.dvkr.screenstream.ui.enableEdgeToEdge
import androidx.compose.ui.graphics.Color

/**
 * Non-exported debug screen used only for repeatable nova 8 visual audits.
 * It renders an explicitly named preview route and is never a production
 * launcher entry or a public intent surface.
 */
public class V5QaActivity : androidx.activity.ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.Theme_ScreenStream)
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarColor = Color(0xFFF2F7FC), navigationBarColor = Color(0xFFF2F7FC))
        MobileAppServices.initialize(applicationContext)
        val route = intent.getStringExtra(EXTRA_QA_ROUTE).orEmpty()
        setContent {
            ScreenStreamTheme {
                V5NativeApp(
                    initialCandidateCardId = null,
                    qaRoute = route,
                    modifier = androidx.compose.ui.Modifier.windowInsetsPadding(WindowInsets.safeDrawing).fillMaxSize(),
                )
            }
        }
    }

    public companion object {
        public const val EXTRA_QA_ROUTE: String = "cn.zhixingzhixue.mobile.qa.ROUTE"
    }
}
