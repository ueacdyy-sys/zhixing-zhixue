package cn.zhixingzhixue.edge.android

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cn.zhixingzhixue.learning.application.KnowledgeGraphRepository
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdgeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeOrigin
import cn.zhixingzhixue.learning.domain.KnowledgeGraphReviewStatus
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.StudentKnowledgeEdgeDraft
import cn.zhixingzhixue.learning.domain.StudentKnowledgeNodeDraft
import kotlinx.coroutines.launch
import java.util.UUID
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Local knowledge vault: PC output is a pending proposal; student-created
 * notes and relationships are committed only through the controls below.
 */
@Composable
public fun StudentKnowledgeGraphContent(
    repository: KnowledgeGraphRepository,
    modifier: Modifier = Modifier,
) {
    val snapshot by repository.observeGraph().collectAsState(initial = KnowledgeGraphSnapshot.empty())
    val profile by repository.observeProfile().collectAsState(initial = emptyList())
    val context = LocalContext.current
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val scope = rememberCoroutineScope()
    var editingNode by remember { mutableStateOf<KnowledgeGraphNode?>(null) }
    var creatingChildOf by remember { mutableStateOf<KnowledgeGraphNode?>(null) }
    var creatingRoot by remember { mutableStateOf(false) }
    var linkingFrom by remember { mutableStateOf<KnowledgeGraphNodeId?>(null) }

    GlassPanel(modifier = modifier.fillMaxWidth()) {
        Row {
            Column(modifier = Modifier.weight(1f)) {
                Text("知识全览", color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
                Text("证据建议与手工笔记共存；待确认建议不会被写成已掌握结论。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
            }
            Button(
                enabled = session != null,
                onClick = { creatingRoot = true },
                colors = ButtonDefaults.buttonColors(containerColor = ZhixingVisualTokens.Quiet, contentColor = ZhixingVisualTokens.Accent),
            ) { Text("新建节点", fontFamily = V5Typography.Family) }
        }
        if (session == null) {
            Spacer(Modifier.height(8.dp))
            Text("开始一次学习会话后可新建手工节点。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        }
        if (snapshot.nodes.isEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text("暂无知识节点。完成连续媒体证据分析后会先进入待确认建议。", color = ZhixingVisualTokens.SecondaryInk, fontFamily = V5Typography.Family)
        } else {
            Spacer(Modifier.height(14.dp))
            KnowledgeGraphCanvas(
                snapshot = snapshot,
                onNodeClick = { editingNode = it },
                onCreateChild = { creatingChildOf = it },
            )
            Spacer(Modifier.height(10.dp))
            snapshot.nodes.forEach { node ->
                GraphNodeRow(
                    node = node,
                    isLinkSource = linkingFrom == node.id,
                    onClick = { editingNode = node },
                    onCreateChild = { creatingChildOf = node },
                    onLink = {
                        val from = linkingFrom
                        when {
                            from == null -> linkingFrom = node.id
                            from == node.id -> linkingFrom = null
                            else -> scope.launch {
                                repository.createStudentEdge(
                                    StudentKnowledgeEdgeDraft(
                                        id = KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()),
                                        from = from,
                                        to = node.id,
                                        relationship = KnowledgeRelationship.RELATED_TO,
                                    ),
                                )
                                linkingFrom = null
                            }
                        }
                    },
                )
                Spacer(Modifier.height(8.dp))
            }
        }
        if (profile.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text("学习分析中有 ${profile.size} 条证据索引，均保留候选属性。", color = ZhixingVisualTokens.Accent, fontFamily = V5Typography.Family)
        }
    }

    val createParent = creatingChildOf
    if (creatingRoot || creatingChildOf != null) {
        KnowledgeNodeEditor(
            title = if (createParent == null) "新建知识节点" else "新建子节点",
            initialLabel = "",
            initialNote = "",
            canDelete = false,
            onDismiss = { creatingRoot = false; creatingChildOf = null },
            onSave = { label, note ->
                val activeSession = session ?: return@KnowledgeNodeEditor
                scope.launch {
                    val refs = createParent?.evidenceRefs.orEmpty()
                    val created = repository.createStudentNode(
                        StudentKnowledgeNodeDraft(
                            id = KnowledgeGraphNodeId("student:" + UUID.randomUUID()),
                            label = label,
                            sessionId = activeSession.id,
                            parentEvidenceRefs = refs,
                            note = note,
                        ),
                    )
                    createParent?.let { parent ->
                        repository.createStudentEdge(
                            StudentKnowledgeEdgeDraft(
                                id = KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()),
                                from = parent.id,
                                to = created.id,
                                relationship = KnowledgeRelationship.PART_OF,
                            ),
                        )
                    }
                    creatingRoot = false
                    creatingChildOf = null
                }
            },
            onDelete = {},
        )
    }
    editingNode?.let { node ->
        KnowledgeNodeEditor(
            title = node.label,
            initialLabel = node.label,
            initialNote = node.note,
            canDelete = node.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED,
            confirmLabel = if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) "确认建议" else "保存",
            onDismiss = { editingNode = null },
            onSave = { label, note ->
                scope.launch {
                    if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) {
                        repository.confirmSuggestion(node.id)
                    } else {
                        repository.updateStudentNode(node.id, label, note)
                    }
                    editingNode = null
                }
            },
            onDelete = {
                scope.launch {
                    repository.removeNode(node.id)
                    editingNode = null
                }
            },
        )
    }
}

@Composable
private fun KnowledgeNodeEditor(
    title: String,
    initialLabel: String,
    initialNote: String,
    canDelete: Boolean,
    confirmLabel: String = "创建",
    onDismiss: () -> Unit,
    onSave: (String, String) -> Unit,
    onDelete: () -> Unit,
) {
    var label by remember(title) { mutableStateOf(initialLabel) }
    var note by remember(title) { mutableStateOf(initialNote) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title, fontFamily = V5Typography.Family) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(value = label, onValueChange = { label = it }, label = { Text("节点名称") }, singleLine = true)
                OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("节点笔记") }, minLines = 3)
            }
        },
        confirmButton = { TextButton(enabled = label.isNotBlank(), onClick = { onSave(label, note) }) { Text(confirmLabel) } },
        dismissButton = {
            Row {
                if (canDelete) TextButton(onClick = onDelete) { Text("删除节点") }
                TextButton(onClick = onDismiss) { Text("取消") }
            }
        },
    )
}

@Composable
private fun KnowledgeGraphCanvas(
    snapshot: KnowledgeGraphSnapshot,
    onNodeClick: (KnowledgeGraphNode) -> Unit,
    onCreateChild: (KnowledgeGraphNode) -> Unit,
) {
    val nodes = snapshot.nodes.take(MAX_VISIBLE_GRAPH_NODES)
    BoxWithConstraints(modifier = Modifier.fillMaxWidth().height(220.dp)) {
        val canvasWidth = maxWidth
        val canvasHeight = maxHeight
        val center = Offset(canvasWidth.value / 2f, canvasHeight.value / 2f)
        val radius = minOf(canvasWidth.value, canvasHeight.value) * 0.33f
        val positions = nodes.mapIndexed { index, _ ->
            val angle = (2.0 * PI * index / nodes.size) - PI / 2.0
            Offset(center.x + (radius * cos(angle)).toFloat(), center.y + (radius * sin(angle)).toFloat())
        }
        Canvas(modifier = Modifier.fillMaxWidth().height(220.dp)) {
            snapshot.edges.forEach { edge ->
                val fromIndex = nodes.indexOfFirst { it.id == edge.from }
                val toIndex = nodes.indexOfFirst { it.id == edge.to }
                if (fromIndex >= 0 && toIndex >= 0) {
                    drawLine(
                        ZhixingVisualTokens.Accent.copy(alpha = 0.38f),
                        Offset(positions[fromIndex].x.dp.toPx(), positions[fromIndex].y.dp.toPx()),
                        Offset(positions[toIndex].x.dp.toPx(), positions[toIndex].y.dp.toPx()),
                        2.dp.toPx(),
                    )
                }
            }
        }
        nodes.forEachIndexed { index, node ->
            val position = positions[index]
            Box(
                modifier = Modifier
                    .offset(x = position.x.dp - 43.dp, y = position.y.dp - 18.dp)
                    .width(86.dp),
            ) {
                Surface(
                    modifier = Modifier.fillMaxWidth().clickable { onNodeClick(node) },
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(9.dp),
                    color = if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) ZhixingVisualTokens.Quiet else ZhixingVisualTokens.AccentSoft,
                    border = androidx.compose.foundation.BorderStroke(1.dp, ZhixingVisualTokens.Accent.copy(alpha = 0.48f)),
                ) {
                    Text(
                        text = node.label.take(10),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 8.dp),
                        color = ZhixingVisualTokens.Ink,
                        fontFamily = V5Typography.Family,
                    )
                }
                TextButton(
                    modifier = Modifier.align(androidx.compose.ui.Alignment.TopEnd).offset(x = 14.dp, y = (-12).dp),
                    onClick = { onCreateChild(node) },
                ) { Text("＋", fontFamily = V5Typography.Family) }
            }
        }
    }
}

@Composable
private fun GraphNodeRow(
    node: KnowledgeGraphNode,
    isLinkSource: Boolean,
    onClick: () -> Unit,
    onCreateChild: () -> Unit,
    onLink: () -> Unit,
) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Column(modifier = Modifier.weight(1f).clickable(onClick = onClick)) {
            Text(node.label, color = ZhixingVisualTokens.Ink, fontFamily = V5Typography.Family, fontWeight = FontWeight.Medium)
            Text(
                if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) "AI 证据建议 · 待确认" else "${node.type.name} · 已确认",
                color = ZhixingVisualTokens.SecondaryInk,
                fontFamily = V5Typography.Family,
            )
        }
        TextButton(onClick = onCreateChild) { Text("＋") }
        TextButton(onClick = onLink) { Text(if (isLinkSource) "取消连接" else "连接") }
    }
}

private const val MAX_VISIBLE_GRAPH_NODES: Int = 12
