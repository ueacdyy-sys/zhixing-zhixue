package cn.zhixingzhixue.edge.android

import android.content.ContentResolver
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.domain.AgentConversationMessage
import cn.zhixingzhixue.learning.domain.AgentMessageAuthor
import cn.zhixingzhixue.learning.domain.AgentResourceAttachment
import cn.zhixingzhixue.learning.domain.AgentResourceState
import java.time.OffsetDateTime
import java.util.UUID
import kotlinx.coroutines.launch

/**
 * Independent local agent workbench. It preserves a real local conversation
 * draft and attachment queue, but will not fabricate search, model or file
 * generation results before a remote service adapter is configured.
 */
@Composable
public fun StudentAgentContent(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val store = remember { MobileAppServices.agentWorkspaceStore(context) }
    val gateway = remember { MobileAppServices.pcAgentGatewayClient(context) }
    val workspace by store.observe().collectAsState(initial = cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot.empty())
    val scope = rememberCoroutineScope()
    var draft by rememberSaveable { mutableStateOf("") }
    var resourcesExpanded by rememberSaveable { mutableStateOf(false) }
    val threadState = rememberLazyListState()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        val attachments = uris.mapNotNull { uri -> context.toLocalAttachment(uri) }
        if (attachments.isNotEmpty()) scope.launch { store.addResources(attachments) }
    }

    LaunchedEffect(workspace.messages.size) {
        if (workspace.messages.isNotEmpty()) threadState.animateScrollToItem(workspace.messages.lastIndex)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(ZhixingVisualTokens.CanvasBottom)
            .padding(start = 16.dp, end = 16.dp, top = 52.dp, bottom = 12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("智能体", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.SemiBold)
                Text("问答、检索与文件任务", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                TextButton(onClick = { resourcesExpanded = !resourcesExpanded }) { Text("资料", fontFamily = V5Typography.Family) }
                TextButton(onClick = { scope.launch { store.beginEmptyConversation() } }) { Text("新会话", fontFamily = V5Typography.Family) }
            }
        }
        if (workspace.contextReferences.isNotEmpty()) {
            LazyRow(
                modifier = Modifier.fillMaxWidth().padding(top = 5.dp, bottom = 7.dp),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                items(workspace.contextReferences, key = { it.id }) { reference ->
                    Surface(shape = RoundedCornerShape(11.dp), color = ZhixingVisualTokens.Quiet) {
                        Text(
                            text = "引用 · ${reference.title}",
                            modifier = Modifier.padding(horizontal = 9.dp, vertical = 6.dp),
                            color = ZhixingVisualTokens.Accent,
                            fontFamily = V5Typography.Family,
                        )
                    }
                }
            }
        }
        if (resourcesExpanded) {
            GlassPanel(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                Text("资料队列", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
                if (workspace.resources.isEmpty()) Text("尚未添加资料。发送时才会经已配对 PC 上传和解析。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                workspace.resources.forEach { resource ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text(resource.displayName, color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
                            Text(
                                when (resource.state) {
                                    AgentResourceState.LOCAL_QUEUED -> "待上传到已配对 PC"
                                    AgentResourceState.UPLOADING -> "正在上传"
                                    AgentResourceState.READY_FOR_AGENT -> "已上传并可供问答引用"
                                    AgentResourceState.FAILED -> resource.errorMessage ?: "上传或解析未完成"
                                },
                                color = ZhixingVisualTokens.SecondaryInk,
                                fontFamily = V5Typography.Family,
                            )
                        }
                        Button(
                            onClick = { scope.launch { store.removeResource(resource.id) } },
                            colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent, contentColor = ZhixingVisualTokens.SecondaryInk),
                        ) { Text("移除", fontFamily = V5Typography.Family) }
                    }
                }
                TextButton(onClick = { picker.launch(arrayOf("*/*")) }) { Text("添加资料", fontFamily = V5Typography.Family) }
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            state = threadState,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (workspace.messages.isEmpty()) {
                item { EmptyAgentThread() }
            }
            items(workspace.messages, key = { it.id }) { message -> AgentMessageRow(message) }
        }
        Surface(
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            shape = RoundedCornerShape(18.dp),
            color = ZhixingVisualTokens.Glass,
            border = androidx.compose.foundation.BorderStroke(1.dp, ZhixingVisualTokens.GlassBorder),
        ) {
            Column(modifier = Modifier.padding(10.dp)) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("输入问题或文件任务", fontFamily = V5Typography.Family) },
                    minLines = 1,
                    maxLines = 4,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { picker.launch(arrayOf("*/*")) }) { Text("＋资料", fontFamily = V5Typography.Family) }
                    TextButton(onClick = { submitAgentRequest(draft, AgentRequestMode.WEB_SEARCH, workspace, store, gateway, context, scope) { draft = it } }, enabled = draft.isNotBlank()) { Text("联网", fontFamily = V5Typography.Family) }
                    TextButton(onClick = { submitAgentRequest(draft, AgentRequestMode.EXPORT_MARKDOWN, workspace, store, gateway, context, scope) { draft = it } }, enabled = draft.isNotBlank()) { Text("生成文件", fontFamily = V5Typography.Family) }
                    Spacer(Modifier.weight(1f))
                    Button(
                        onClick = { submitAgentRequest(draft, AgentRequestMode.ANSWER, workspace, store, gateway, context, scope) { draft = it } },
                        enabled = draft.isNotBlank(),
                        colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Accent, contentColor = Color.White),
                    ) { Text("发送", fontFamily = V5Typography.Family) }
                }
            }
        }
    }
}

@Composable
private fun EmptyAgentThread() {
    Column(modifier = Modifier.padding(top = 26.dp, start = 8.dp, end = 8.dp)) {
        Text("从这里开始", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(6.dp))
        Text("可直接提问、联网检索或描述需要生成的文件。发现页选中的会话会作为可见引用带入这里。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
    }
}

@Composable
private fun AgentMessageRow(message: AgentConversationMessage) {
    val isStudent = message.author == AgentMessageAuthor.STUDENT
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isStudent) Arrangement.End else Arrangement.Start,
        verticalAlignment = Alignment.Top,
    ) {
        if (!isStudent) {
            Surface(shape = RoundedCornerShape(8.dp), color = ZhixingVisualTokens.Quiet) {
                Text("智", modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), color = ZhixingVisualTokens.Accent, fontFamily = V5Typography.Family, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(1.dp).weight(0.04f))
        }
        Surface(
            modifier = Modifier.fillMaxWidth(0.82f),
            shape = RoundedCornerShape(16.dp),
            color = if (isStudent) ZhixingVisualTokens.AccentSoft else ZhixingVisualTokens.Glass,
            border = androidx.compose.foundation.BorderStroke(1.dp, ZhixingVisualTokens.GlassBorder),
        ) {
            Column(modifier = Modifier.padding(11.dp)) {
                Text(message.body, color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family)
                Spacer(Modifier.height(3.dp))
                Text(message.createdAt.toLocalTime().withSecond(0).toString(), color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            }
        }
    }
}

private fun submitAgentRequest(
    draft: String,
    mode: AgentRequestMode,
    workspace: cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot,
    store: AndroidAgentWorkspaceStore,
    gateway: PcAgentGatewayClient,
    context: android.content.Context,
    scope: kotlinx.coroutines.CoroutineScope,
    clearDraft: (String) -> Unit,
) {
    val body = draft.trim()
    if (body.isEmpty()) return
    clearDraft("")
    scope.launch {
        store.appendMessage(
            AgentConversationMessage(
                id = UUID.randomUUID().toString(),
                author = AgentMessageAuthor.STUDENT,
                body = body,
                createdAt = OffsetDateTime.now(),
            ),
        )
        val preparedWorkspace = uploadQueuedResources(context, workspace, store, gateway)
        runCatching { gateway.submit(mode, body, preparedWorkspace) }
            .onSuccess { run ->
                if (run.state == "SUCCEEDED" && !run.answer.isNullOrBlank()) {
                    store.appendMessage(
                        AgentConversationMessage(
                            id = UUID.randomUUID().toString(),
                            author = AgentMessageAuthor.ASSISTANT,
                            body = run.answer,
                            createdAt = OffsetDateTime.now(),
                            remoteRunId = run.runId,
                        ),
                    )
                    run.artifact?.let { artifact ->
                        gateway.downloadArtifact(context, artifact)
                        store.appendMessage(
                            AgentConversationMessage(
                                id = UUID.randomUUID().toString(),
                                author = AgentMessageAuthor.SYSTEM,
                                body = "文件已通过已配对 PC 的安全连接保存到下载目录：${artifact.displayName}",
                                createdAt = OffsetDateTime.now(),
                            ),
                        )
                    }
                } else {
                    val detail = run.errorMessage ?: run.errorCode ?: "PC 智能体未返回可用结果。"
                    store.appendMessage(
                        AgentConversationMessage(
                            id = UUID.randomUUID().toString(),
                            author = AgentMessageAuthor.SYSTEM,
                            body = "本次请求未完成：$detail",
                            createdAt = OffsetDateTime.now(),
                        ),
                    )
                }
            }
            .onFailure { error ->
                store.appendMessage(
                    AgentConversationMessage(
                        id = UUID.randomUUID().toString(),
                        author = AgentMessageAuthor.SYSTEM,
                        body = "无法连接已配对 PC：${error.message?.take(180) ?: "网络请求失败"}",
                        createdAt = OffsetDateTime.now(),
                    ),
                )
            }
    }
}

internal suspend fun uploadQueuedResources(
    context: android.content.Context,
    workspace: cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot,
    store: AndroidAgentWorkspaceStore,
    gateway: PcAgentGatewayClient,
): cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot {
    val updated = workspace.resources.map { resource ->
        if (resource.state == AgentResourceState.READY_FOR_AGENT) return@map resource
        store.updateResource(resource.copy(state = AgentResourceState.UPLOADING, errorMessage = null))
        val result = runCatching { gateway.uploadResource(context, resource) }
        val next = result.fold(
            onSuccess = { upload ->
                resource.copy(
                    state = if (upload.state == "READY_FOR_AGENT") AgentResourceState.READY_FOR_AGENT else AgentResourceState.FAILED,
                    sha256 = upload.sha256,
                    errorMessage = upload.errorMessage,
                )
            },
            onFailure = { error -> resource.copy(state = AgentResourceState.FAILED, errorMessage = error.message?.take(180) ?: "资料上传失败") },
        )
        store.updateResource(next)
        next
    }
    return workspace.copy(resources = updated)
}

internal fun android.content.Context.toLocalAttachment(uri: Uri): AgentResourceAttachment? = runCatching {
    contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
    val name = contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        cursor.takeIf { it.moveToFirst() }?.getString(cursor.getColumnIndexOrThrow(OpenableColumns.DISPLAY_NAME))
    } ?: uri.lastPathSegment ?: "未命名资料"
    AgentResourceAttachment(
        id = UUID.randomUUID().toString(),
        uri = uri.toString(),
        displayName = name,
        mimeType = contentResolver.getType(uri),
        addedAt = OffsetDateTime.now(),
    )
}.getOrNull()
