package info.dvkr.screenstream.ui

import android.Manifest
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import cn.zhixingzhixue.edge.android.V5NativeApp
import info.dvkr.screenstream.common.isPermissionGranted
import info.dvkr.screenstream.network.LocalNetworkPermission
import info.dvkr.screenstream.notification.NotificationPermission

/** Entry point: the former Compose front-end is no longer part of the route tree. */
@Composable
internal fun ScreenStreamContent(
    modifier: Modifier = Modifier,
    initialCandidateCardId: String? = null,
    initialOpenL1: Boolean = false,
) {
    V5NativeApp(
        initialCandidateCardId = initialCandidateCardId,
        initialOpenL1 = initialOpenL1,
        modifier = modifier.windowInsetsPadding(WindowInsets.safeDrawing).fillMaxSize(),
    )

    val context = LocalContext.current
    val notificationMissing = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
        !context.isPermissionGranted(Manifest.permission.POST_NOTIFICATIONS)
    val localNetworkEnabled = rememberSaveable { mutableStateOf(!notificationMissing) }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        NotificationPermission(onCanRequestNextPermissionChange = { localNetworkEnabled.value = it })
    }
    if (Build.VERSION.SDK_INT >= 37) LocalNetworkPermission(enabled = localNetworkEnabled.value)

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            (view.context as ComponentActivity).apply {
                enableEdgeToEdge(statusBarColor = Color(0xFFF2F7FC), navigationBarColor = Color(0xFFF2F7FC))
                window.decorView.setBackgroundColor(Color(0xFFF2F7FC).toArgb())
            }
        }
    }
}
