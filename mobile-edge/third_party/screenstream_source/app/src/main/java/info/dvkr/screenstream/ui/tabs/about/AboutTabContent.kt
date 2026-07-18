package info.dvkr.screenstream.ui.tabs.about

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import info.dvkr.screenstream.R
import info.dvkr.screenstream.common.getVersionName

@Composable
public fun AboutTabContent(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {

        Image(
            painter = painterResource(id = R.drawable.logo),
            contentDescription = null,
            modifier = Modifier
                .padding(top = 8.dp)
                .size(104.dp)
                .clip(MaterialTheme.shapes.medium)
        )

        Text(
            text = stringResource(id = R.string.app_name),
            modifier = Modifier.padding(top = 16.dp),
            maxLines = 1,
            style = MaterialTheme.typography.headlineSmall
        )

        val context = androidx.compose.ui.platform.LocalContext.current
        Text(
            text = stringResource(id = R.string.app_tab_about_app_version, context.getVersionName()),
            modifier = Modifier.padding(16.dp),
            style = MaterialTheme.typography.titleMedium
        )

        Text(
            text = stringResource(id = R.string.app_tab_about_developer_name),
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
        )

        Text(
            text = "本应用仅在学生主动授权后进行本地媒体传输；候选与证据默认留在本机。第三方 ScreenStream MIT 许可见项目内 THIRD_PARTY_NOTICES。",
            modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
            style = MaterialTheme.typography.bodyMedium
        )
    }
}
