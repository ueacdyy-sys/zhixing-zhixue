package cn.zhixingzhixue.edge.android

import android.content.Intent
import android.provider.Settings
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredHeight
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.sp
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.AgentConversationMessage
import cn.zhixingzhixue.learning.domain.AgentContextReference
import cn.zhixingzhixue.learning.domain.AgentMessageAuthor
import cn.zhixingzhixue.learning.domain.AgentResourceAttachment
import cn.zhixingzhixue.learning.domain.AgentKnowledgeReference
import cn.zhixingzhixue.learning.domain.AgentResourceState
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.LearningStage
import cn.zhixingzhixue.learning.domain.StudentLearningAction
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdgeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeOrigin
import cn.zhixingzhixue.learning.domain.KnowledgeGraphReviewStatus
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.StudentKnowledgeEdgeDraft
import cn.zhixingzhixue.learning.domain.StudentKnowledgeNodeDraft
import kotlinx.coroutines.launch
import java.time.OffsetDateTime
import java.util.UUID
import info.dvkr.screenstream.rtsp.RtspTransportFacade
import info.dvkr.screenstream.rtsp.RtspTransportSnapshot
import info.dvkr.screenstream.rtsp.RtspTransportStatus
import info.dvkr.screenstream.rtsp.RtspStreamingModule
import info.dvkr.screenstream.common.module.StreamingModuleManager
import info.dvkr.screenstream.rtsp.settings.RtspSettings
import info.dvkr.screenstream.common.settings.AppSettings
import info.dvkr.screenstream.common.ui.mediaprojection.ScreenCapturePermissionFlow
import info.dvkr.screenstream.common.ui.mediaprojection.rememberScreenCaptureStartRequester
import org.koin.core.context.GlobalContext
import org.koin.core.component.get
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * Native reimplementation of the approved V5 information architecture.
 *
 * This is intentionally independent of the retired `Student*Content` views:
 * every page, route and control is composed from the V5 visual grammar.  The
 * candidate store remains the live source for capture results; unavailable
 * future hardware features are rendered as unavailable rather than invented.
 */
@Composable
public fun V5NativeApp(
    initialCandidateCardId: String?,
    initialOpenL1: Boolean = false,
    modifier: Modifier = Modifier,
    qaRoute: String? = null,
) {
    val qa = remember(qaRoute) { V5QaPreview.parse(qaRoute) }
    val context = LocalContext.current
    // L1 is a system heads-up message, never a Discover-page banner.
    // Registering its channel here posts nothing; it only makes Android's own
    // channel settings reachable before the first eligible PC candidate arrives.
    LaunchedEffect(context) { AndroidStudentNotice(context.applicationContext).ensureChannel() }
    val baseDensity = LocalDensity.current
    val uiPreferences = remember(context) { context.getSharedPreferences("v5_ui_preferences", android.content.Context.MODE_PRIVATE) }
    // V5 的“标准”字号必须尊重系统字号；此前把 1.10 当成标准，会在
    // 部分华为系统字体上压缩分段控件的字形下沿。兼容旧值时迁移回 1.00。
    val storedTextScale = uiPreferences.getFloat("text_scale_multiplier", 1.00F)
    var textScaleMultiplier by remember { mutableFloatStateOf(if (storedTextScale == 1.10F) 1.00F else storedTextScale) }
    LaunchedEffect(storedTextScale) {
        if (storedTextScale == 1.10F) uiPreferences.edit().putFloat("text_scale_multiplier", 1.00F).apply()
    }
    val scope = rememberCoroutineScope()
    val agentWorkspaceStore = remember { MobileAppServices.agentWorkspaceStore(context) }
    val pcDeliveryClient = remember { MobileAppServices.pcDeliveryClient(context) }
    val candidates by remember { MobileAppServices.candidateStore(context) }.observe().collectAsState(initial = emptyList())
    // Discover must reflect the media transport, not whether a candidate was
    // previously received. Candidate persistence and active capture are two
    // independent facts.
    val discoverTransportFacade = rememberStartedRtspFacade()
    val discoverTransportFallback = remember { MutableStateFlow(RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null)) }
    val discoverTransport by (discoverTransportFacade?.state ?: discoverTransportFallback).collectAsState()
    val pcLink = remember { MobileAppServices.pcLinkStore(context) }.read()
    var primary by rememberSaveable(qaRoute) { mutableStateOf(qa.primary) }
    var route by rememberSaveable(qaRoute, initialCandidateCardId, initialOpenL1) {
        mutableStateOf(if (initialOpenL1 && !initialCandidateCardId.isNullOrBlank()) V5Route.CONTENT else qa.route)
    }
    var drawerOpen by rememberSaveable(qaRoute) { mutableStateOf(qa.drawerOpen) }
    var stream by rememberSaveable(qaRoute) { mutableStateOf(qa.stream) }
    var selectedCandidateId by rememberSaveable(qaRoute, initialCandidateCardId) { mutableStateOf(qa.candidateId ?: initialCandidateCardId) }
    var discoverResetKey by rememberSaveable { mutableStateOf(0) }
    var discoverSelectionRequest by rememberSaveable { mutableStateOf(0) }
    var profileView by rememberSaveable(qaRoute) { mutableStateOf(qa.profileView) }
    var chart by rememberSaveable(qaRoute) { mutableStateOf(qa.chart) }
    // 学习分析的筛选是统计状态，不是筛选页里一次性的“已选择”提示。
    // 它与图表、全屏画布共用同一索引，返回统计页后必须立即可见。
    var analysisFilterIndex by rememberSaveable(qaRoute) { mutableStateOf(0) }
    var agentLibraryOpen by rememberSaveable(qaRoute) { mutableStateOf(qa.agentLibraryOpen) }
    var agentSessionReferenceCount by rememberSaveable { mutableStateOf(0) }
    var trashedSessionIds by rememberSaveable { mutableStateOf(emptySet<String>()) }
    var settingsSection by rememberSaveable(qaRoute) { mutableStateOf(qa.settingsSection) }
    // A history entry carries the complete destination context.  Saving only a
    // route enum caused detail pages to return with the child page title and
    // subject still attached.
    var routeHistory by rememberSaveable { mutableStateOf(emptyList<String>()) }
    var secondaryTitle by rememberSaveable(qaRoute) { mutableStateOf(qa.secondaryTitle) }
    var secondarySubject by rememberSaveable(qaRoute) { mutableStateOf(qa.secondarySubject) }
    var toastMessage by rememberSaveable { mutableStateOf<String?>(null) }
    // 设置抽屉不是路由栈中的一页；它覆盖的是用户打开菜单前的精确页面。
    // 单独保存覆盖目标，避免“设置 → 媒体设置 → 返回”只弹一层后露出错误页面。
    var drawerOriginRoute by rememberSaveable { mutableStateOf(V5Route.HOME) }
    var drawerOriginPrimary by rememberSaveable { mutableStateOf(V5Primary.DISCOVER) }
    var drawerOriginTitle by rememberSaveable { mutableStateOf("") }
    var drawerOriginSubject by rememberSaveable { mutableStateOf("") }
    var drawerOriginHistory by rememberSaveable { mutableStateOf(emptyList<String>()) }

    val navigate: (V5Route, String, String) -> Unit = { target, title, subject ->
        routeHistory = routeHistory + listOf(route.name, secondaryTitle, secondarySubject).joinToString(NAV_ENTRY_SEPARATOR)
        if ((target == V5Route.CONTENT || target == V5Route.EVIDENCE_ITEM) && candidates.any { it.id.value == subject }) selectedCandidateId = subject
        secondaryTitle = title
        secondarySubject = subject
        route = target
    }
    val goBack: () -> Unit = {
        if (routeHistory.isNotEmpty()) {
            val entry = routeHistory.last().split(NAV_ENTRY_SEPARATOR, limit = 3)
            route = V5Route.valueOf(entry[0])
            secondaryTitle = entry.getOrElse(1) { "" }
            secondarySubject = entry.getOrElse(2) { "" }
            routeHistory = routeHistory.dropLast(1)
        } else {
            route = V5Route.HOME
        }
    }
    // Settings entered from the drawer are a transient secondary layer.  Both
    // the visible return control and Android system Back must restore that
    // layer, including for the media setting pages which render their controls
    // directly in V5MediaControlsPage.
    val returnToSettingsDrawer: () -> Unit = {
        settingsSection = null
        route = drawerOriginRoute
        primary = drawerOriginPrimary
        secondaryTitle = drawerOriginTitle
        secondarySubject = drawerOriginSubject
        routeHistory = drawerOriginHistory
        drawerOpen = true
    }
    val openDrawer: () -> Unit = {
        drawerOriginRoute = route
        drawerOriginPrimary = primary
        drawerOriginTitle = secondaryTitle
        drawerOriginSubject = secondarySubject
        drawerOriginHistory = routeHistory
        drawerOpen = true
    }

    BackHandler(enabled = drawerOpen || agentLibraryOpen || route != V5Route.HOME || primary != V5Primary.DISCOVER) {
        when {
            drawerOpen -> drawerOpen = false
            agentLibraryOpen -> agentLibraryOpen = false
            route == V5Route.SETTINGS || (route == V5Route.MEDIA && settingsSection != null) -> returnToSettingsDrawer()
            route == V5Route.HOME -> primary = V5Primary.DISCOVER
            else -> goBack()
        }
    }

    CompositionLocalProvider(LocalDensity provides Density(baseDensity.density, baseDensity.fontScale * textScaleMultiplier)) {
    Box(modifier = modifier.background(NativeV5Tokens.Canvas)) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f)) {
        when (route) {
            V5Route.HOME -> when (primary) {
                V5Primary.DISCOVER -> V5DiscoverPage(
                    candidates = candidates,
                    stream = stream,
                    qaFixtureEnabled = qaRoute != null,
                    selectedCandidateId = selectedCandidateId,
                    resetKey = discoverResetKey,
                    selectionRequestToken = discoverSelectionRequest,
                    onStream = { stream = it },
                    onOpenCandidate = { id, isLearningEligible ->
                        // The V5 web prototype records incomplete evidence but does not
                        // turn it into a voluntary L0–L4 learning path.  Keep the same
                        // rule in the native entry point; a card being visible is not
                        // permission to create a learning interaction.
                        if (!isLearningEligible) {
                            toastMessage = "证据尚未补全，仅保留记录，暂不能进入学习路径"
                        } else {
                            selectedCandidateId = id
                            navigate(V5Route.CONTENT, "分级学习", id)
                        }
                    },
                    onAskAgent = { references ->
                        agentSessionReferenceCount = references.size
                        scope.launch { agentWorkspaceStore.replaceContextReferences(references) }
                        primary = V5Primary.AGENT
                        toastMessage = "已带入 ${references.size} 条会话引用"
                    },
                    trashedSessionIds = trashedSessionIds,
                    onTrashSessions = { ids -> trashedSessionIds = trashedSessionIds + ids },
                    onOpenSecondary = { target, title, subject -> navigate(target, title, subject) },
                    onToast = { toastMessage = it },
                )
                V5Primary.ANALYSIS -> V5AnalysisPage(
                    candidates = candidates,
                    profileView = profileView,
                    chart = chart,
                    analysisFilterIndex = analysisFilterIndex,
                    onProfileView = { profileView = it },
                    onChart = { chart = it },
                    onOpenCanvas = { kind -> navigate(V5Route.CANVAS, if (kind.startsWith("stats:")) "学习分析统计" else "知识脉络", kind) },
                    onOpenSecondary = { target, title, subject -> navigate(target, title, subject) },
                    onSyncAiGraph = {
                        scope.launch {
                            toastMessage = runCatching { pcDeliveryClient.synchronizeOnce() }
                                .fold(
                                    onSuccess = { count -> if (count > 0) "已同步 $count 项 AI 图谱建议" else "暂无待同步的 AI 图谱建议" },
                                    onFailure = { error -> "AI 图谱同步失败：${error.message?.take(80) ?: "连接失败"}" },
                                )
                        }
                    },
                )
                V5Primary.AGENT -> V5AgentPage(
                    libraryOpen = agentLibraryOpen,
                    sessionReferenceCount = agentSessionReferenceCount,
                    onLibrary = { agentLibraryOpen = it },
                    onOpenDiscoverSelection = { primary = V5Primary.DISCOVER; agentLibraryOpen = false; discoverSelectionRequest += 1 },
                )
                V5Primary.CONNECTION -> V5ConnectionPage(pcPaired = pcLink != null, onOpenControls = { navigate(V5Route.MEDIA, "媒体会话", "") }, onOpenSecondary = { target, title, subject -> navigate(target, title, subject) })
            }
            V5Route.CONTENT -> V5LearningDetail(
                candidate = candidates.firstOrNull { it.id.value == selectedCandidateId }
                    ?: candidates.lastOrNull { it.source == stream },
                displayTitle = when (selectedCandidateId) {
                    "prototype-poetry" -> "古诗词意象"
                    "prototype-history" -> "宋代城市与商业"
                    "prototype-glasses-city" -> "城市空间与建筑观察"
                    "prototype-glasses-park" -> "植物形态与城市绿地"
                    else -> null
                },
                canOfferLearningLevels = ((qaRoute != null || selectedCandidateId == "prototype-glasses-city") && selectedCandidateId != "prototype-poetry") || (candidates.firstOrNull { it.id.value == selectedCandidateId }?.isL1Eligible == true),
                qaPreviewLevel = qa.contentLevel,
                initialRequestedLevel = if (initialOpenL1) 1 else null,
                qaPreviewMapMode = qa.contentMapMode,
                onBack = { discoverResetKey += 1; goBack() },
                onOpenCanvas = { mapMode -> navigate(V5Route.CANVAS, "内容关系图", "content:$mapMode") },
                onOpenSecondary = { target, title, subject -> navigate(target, title, subject) },
            )
            V5Route.CANVAS -> V5FullKnowledgeCanvas(
                title = secondaryTitle.ifBlank { "知识脉络" },
                kind = secondarySubject,
                analysisFilterIndex = analysisFilterIndex,
                onBack = goBack,
                onOpenContentNode = { label -> navigate(V5Route.CONCEPT_DETAIL, "概念节点", label) },
                onOpenKnowledgeNode = { node -> navigate(V5Route.NODE_DETAIL, "知识节点笔记", node.label) },
                onCreateKnowledgeChild = { parent -> navigate(V5Route.KNOWLEDGE_CREATE, "新建知识节点", parent?.label.orEmpty()) },
            )
            V5Route.SETTINGS -> V5SettingsPage(
                initialSection = settingsSection,
                onBack = goBack,
                onReturnToDrawer = returnToSettingsDrawer,
                onOpenMediaSession = { section -> navigate(V5Route.MEDIA, section, section) },
                onOpenSecondary = { target, title, subject -> navigate(target, title, subject) },
                textScaleMultiplier = textScaleMultiplier,
                onTextScaleMultiplier = { value ->
                    textScaleMultiplier = value
                    uiPreferences.edit().putFloat("text_scale_multiplier", value).apply()
                },
            )
            V5Route.MEDIA -> V5MediaControlsPage(
                section = secondarySubject.ifBlank { null },
                onBack = if (settingsSection != null) returnToSettingsDrawer else goBack,
            )
            V5Route.AGENT_CONFIG -> V5AgentServicePage(
                onBack = if (settingsSection == "智能体与服务") returnToSettingsDrawer else goBack,
                onOpenConnection = {
                    route = V5Route.HOME
                    routeHistory = emptyList()
                    primary = V5Primary.CONNECTION
                },
            )
            else -> V5SecondaryInteractionPage(
                route = route,
                title = secondaryTitle,
                subject = secondarySubject,
                activeCandidate = candidates.firstOrNull { it.id.value == selectedCandidateId }
                    ?: candidates.lastOrNull { it.source == stream },
                analysisFilterIndex = analysisFilterIndex,
                onApplyAnalysisFilter = { analysisFilterIndex = it },
                onBack = goBack,
                onOpen = { target, detailTitle, detailSubject -> navigate(target, detailTitle, detailSubject) },
            )
        }

                V5TopBar(
                    onMenu = openDrawer,
                    modifier = Modifier.align(Alignment.TopCenter),
                )
            }
            if (route == V5Route.HOME) {
                V5BottomNav(primary = primary, onPrimary = { primary = it })
            }
        }
        AnimatedVisibility(visible = drawerOpen, enter = fadeIn(), exit = fadeOut()) {
            V5SettingsDrawer(
                onDismiss = { drawerOpen = false },
                onOpenSettings = { section ->
                    drawerOpen = false
                    settingsSection = section
                    if (section in V5_DIRECT_MEDIA_SETTING_SECTIONS) {
                        navigate(V5Route.MEDIA, section, section)
                    } else if (section == "智能体与服务") {
                        navigate(V5Route.AGENT_CONFIG, "智能体与服务", "")
                    } else {
                        navigate(V5Route.SETTINGS, section, "")
                    }
                },
                onOpenConnection = { drawerOpen = false; primary = V5Primary.CONNECTION },
            )
        }
        toastMessage?.let { message ->
            V5Toast(message = message, onDismiss = { toastMessage = null }, modifier = Modifier.align(Alignment.BottomCenter))
        }
    }
    }
}

internal enum class V5Primary(val label: String, val icon: V5Icon) {
    DISCOVER("发现", V5Icon.DISCOVER),
    ANALYSIS("学习分析", V5Icon.ANALYTICS),
    AGENT("智能体", V5Icon.AGENT),
    CONNECTION("连接", V5Icon.CONNECTION),
}

private enum class V5Route {
    HOME, CONTENT, CANVAS, SETTINGS, MEDIA,
    EVIDENCE, SOURCES, SOURCE_DETAIL, NODE_DETAIL, CONCEPT_DETAIL, FILTER, PROFILE_EVIDENCE, EVIDENCE_ITEM,
    SESSION_DETAIL, PC_DETAIL, DEVICE_DETAIL, NOTICE_HISTORY, EXPORT, AUDIT,
    KNOWLEDGE_CREATE, KNOWLEDGE_SEARCH, KNOWLEDGE_TOOLS, KNOWLEDGE_NOTE, KNOWLEDGE_LINK,
    KNOWLEDGE_RENAME, KNOWLEDGE_DELETE, KNOWLEDGE_SOURCE, SENSOR_STATUS, AGENT_CONFIG,
}

/** Debug-only review routes use this declarative state; production passes null. */
private data class V5QaPreview(
    val primary: V5Primary = V5Primary.DISCOVER,
    val route: V5Route = V5Route.HOME,
    val drawerOpen: Boolean = false,
    val stream: CandidateMediaSource = CandidateMediaSource.PHONE_SCREEN,
    val candidateId: String? = null,
    val contentLevel: Int? = null,
    val contentMapMode: Int = 0,
    val profileView: V5ProfileView = V5ProfileView.KNOWLEDGE,
    val chart: V5Chart = V5Chart.SCATTER,
    val settingsSection: String? = null,
    val secondaryTitle: String = "",
    val secondarySubject: String = "",
    val agentLibraryOpen: Boolean = false,
) {
    companion object {
        fun parse(value: String?): V5QaPreview {
            val text = value.orEmpty()
            return when {
                text == "discover" -> V5QaPreview()
                text == "drawer" -> V5QaPreview(drawerOpen = true)
                text == "glasses-discover" -> V5QaPreview(stream = CandidateMediaSource.GLASSES_FIRST_PERSON)
                text.startsWith("content:") -> V5QaPreview(route = V5Route.CONTENT, candidateId = if (text.contains("glasses")) "prototype-glasses" else "prototype-ai", contentLevel = text.substringAfter(':').substringBefore(':').toIntOrNull()?.coerceIn(0, 4), contentMapMode = if (text.contains("map1")) 1 else 0, stream = if (text.contains("glasses")) CandidateMediaSource.GLASSES_FIRST_PERSON else CandidateMediaSource.PHONE_SCREEN)
                text.startsWith("profile:") -> V5QaPreview(primary = V5Primary.ANALYSIS, profileView = V5ProfileView.STATS, chart = V5Chart.entries.firstOrNull { it.name.equals(text.substringAfterLast(':'), true) } ?: V5Chart.SCATTER)
                text == "knowledge" -> V5QaPreview(primary = V5Primary.ANALYSIS)
                text == "connection" -> V5QaPreview(primary = V5Primary.CONNECTION)
                text == "agent" -> V5QaPreview(primary = V5Primary.AGENT)
                text == "agent-library" -> V5QaPreview(primary = V5Primary.AGENT, agentLibraryOpen = true)
                text.startsWith("setting:") -> {
                    val section = text.substringAfter(':')
                    if (section in V5_DIRECT_MEDIA_SETTING_SECTIONS) {
                        V5QaPreview(route = V5Route.MEDIA, settingsSection = section, secondaryTitle = section, secondarySubject = section)
                    } else {
                        V5QaPreview(route = V5Route.SETTINGS, settingsSection = section)
                    }
                }
                text.startsWith("media:") -> V5QaPreview(route = V5Route.MEDIA, secondaryTitle = text.substringAfter(':'), secondarySubject = text.substringAfter(':'))
                text.startsWith("secondary:") -> {
                    val payload = text.substringAfter(':')
                    val name = payload.substringBefore(':')
                    val fixtureSubject = payload.substringAfter(':', "").takeIf { it.isNotBlank() }
                    val target = runCatching { V5Route.valueOf(name) }.getOrDefault(V5Route.EVIDENCE)
                    V5QaPreview(route = target, secondaryTitle = V5_QA_SECONDARY_TITLES[name] ?: name, secondarySubject = fixtureSubject ?: "生成式 AI")
                }
                text.startsWith("canvas:") -> V5QaPreview(route = V5Route.CANVAS, secondaryTitle = "画布", secondarySubject = text.substringAfter(':'))
                else -> V5QaPreview()
            }
        }
    }
}

private const val NAV_ENTRY_SEPARATOR: String = "\u001f"
private val V5_DIRECT_MEDIA_SETTING_SECTIONS: Set<String> = setOf("公开媒体会话", "视频", "音频", "网络")
private val V5_QA_SECONDARY_TITLES: Map<String, String> = mapOf(
    "EVIDENCE" to "捕获窗口与证据",
    "SOURCES" to "材料与实例",
    "SOURCE_DETAIL" to "材料摘要",
    "CONCEPT_DETAIL" to "概念节点",
    "NODE_DETAIL" to "知识节点笔记",
    "KNOWLEDGE_CREATE" to "新建知识节点",
    "KNOWLEDGE_LINK" to "建立双向链接",
    "KNOWLEDGE_RENAME" to "重命名节点",
    "KNOWLEDGE_DELETE" to "删除节点",
    "KNOWLEDGE_SEARCH" to "检索知识节点",
    "KNOWLEDGE_TOOLS" to "图谱管理",
    "KNOWLEDGE_NOTE" to "知识节点笔记",
    "KNOWLEDGE_SOURCE" to "节点来源证据",
    "NOTICE_HISTORY" to "通知历史",
    "EXPORT" to "本地数据导出",
    "AUDIT" to "删除审计",
    "FILTER" to "统计范围",
    "PROFILE_EVIDENCE" to "画像证据",
    "EVIDENCE_ITEM" to "可追溯证据",
    "SESSION_DETAIL" to "会话详情",
    "PC_DETAIL" to "PC 中枢详情",
    "DEVICE_DETAIL" to "设备连接",
    "SENSOR_STATUS" to "状态流与质量",
)
private enum class V5ProfileView { KNOWLEDGE, STATS }
private enum class V5Chart(val label: String) { VENN("韦恩图"), SET("集合图"), SCATTER("散点图"), PIE("饼状图"), BAR("柱状图"), LINE("折线图") }
internal enum class V5Icon { MENU, BACK, FORWARD, DISCOVER, ANALYTICS, AGENT, CONNECTION, ADD, EXPAND, ATTACH, NETWORK, SEND }

private val V5_ANALYSIS_FILTERS: List<String> = listOf(
    "全部已记录",
    "最近 7 天（有时间锚）",
    "手机公开媒体来源",
    "主动学习回执",
)

/**
 * Explicit QA fixtures for screenshot and interaction regression routes.
 * Production startup never renders these records or forwards them to the
 * agent context; only real candidate-card repository entries are user data.
 */
private data class V5PrototypeMessage(
    val id: String,
    val title: String,
    val summary: String,
    val meta: String,
    val status: String,
    val complete: Boolean,
)

private val V5PhonePrototypeMessages = listOf(
    V5PrototypeMessage("prototype-ai", "生成式 AI 与数字媒体", "虚拟演员内容关联到数字媒体、版权与生成式 AI。", "18:31–18:58 · 三模态证据完整", "完整证据", true),
    V5PrototypeMessage("prototype-poetry", "古诗词意象", "证据尚在补全：仅保留记录，不推送学习提醒。", "18:24–18:30 · 音频缺失", "仅记录", false),
)
private val V5PhoneSavedPrototypeMessage = V5PrototypeMessage("prototype-history", "宋代城市与商业", "已从最近一次会话保存，可继续从 L1 小结进入。", "昨天 · 保存到知识脉络", "已保存", true)
private val V5GlassesPrototypeMessages = listOf(
    V5PrototypeMessage("prototype-glasses-city", "城市空间与建筑观察", "第一视角片段已关联时间锚点。", "14:06–14:18 · 已封存", "完整证据", true),
    V5PrototypeMessage("prototype-glasses-park", "植物形态与城市绿地", "片段已封存，等待补齐同源证据。", "13:42–13:47 · 已封存", "仅记录", false),
)

/** Builds immutable, read-only Discover references before entering the agent. */
private fun V5DiscoverReferences(
    selectedIds: Set<String>,
    records: List<CandidateCard>,
    stream: CandidateMediaSource,
    includeQaFixtures: Boolean,
): List<AgentContextReference> {
    val real = records.filter { it.id.value in selectedIds }.map { card ->
        AgentContextReference(card.id.value, card.displayExcerpt.take(240), card.displayExcerpt.take(600), card.source, card.visitId, card.evidenceRefs)
    }
    val prototype = if (!includeQaFixtures && stream != CandidateMediaSource.GLASSES_FIRST_PERSON) emptyList() else (V5PhonePrototypeMessages + V5PhoneSavedPrototypeMessage + V5GlassesPrototypeMessages)
        .filter { it.id in selectedIds }
        .map { item ->
            AgentContextReference(
                id = item.id,
                title = item.title,
                summary = item.summary,
                source = if (item.id.startsWith("prototype-glasses")) CandidateMediaSource.GLASSES_FIRST_PERSON else stream,
                visitId = "prototype:${item.id}",
                evidenceRefs = listOf(LocalEvidenceRef("prototype:${item.id}:evidence")),
            )
        }
    return (real + prototype).distinctBy { it.id }
}

@Composable
private fun V5TopBar(onMenu: () -> Unit, modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxWidth().height(48.dp).padding(horizontal = 16.dp, vertical = 8.dp)) {
        Surface(shape = RoundedCornerShape(9.dp), color = Color(0xF7FFFFFF), shadowElevation = 1.dp, modifier = Modifier.align(Alignment.CenterStart)) {
            IconButton(onClick = onMenu, modifier = Modifier.size(32.dp)) {
                V5LineIcon(V5Icon.MENU, contentDescription = "打开设置抽屉", modifier = Modifier.size(18.dp))
            }
        }
    }
}

@Composable
private fun V5BottomNav(primary: V5Primary, onPrimary: (V5Primary) -> Unit, modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, bottom = 8.dp).height(58.dp)) {
        Surface(modifier = Modifier.fillMaxSize(), shape = RoundedCornerShape(16.dp), color = Color(0xF8FBFDFF), shadowElevation = 5.dp) {
            Row(modifier = Modifier.fillMaxSize().padding(horizontal = 5.dp), verticalAlignment = Alignment.CenterVertically) {
            V5Primary.entries.forEach { item ->
                val active = item == primary
                TextButton(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    onClick = { onPrimary(item) },
                    shape = RoundedCornerShape(13.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                        V5LineIcon(
                            icon = item.icon,
                            tint = if (active) NativeV5Tokens.Accent else NativeV5Tokens.IconMuted,
                            contentDescription = "切换到${item.label}",
                            modifier = Modifier.size(19.dp),
                        )
                        Text(item.label, color = if (active) NativeV5Tokens.Accent else NativeV5Tokens.IconMuted, fontSize = 10.sp, lineHeight = 12.sp, fontWeight = if (active) FontWeight.Bold else FontWeight.Medium, fontFamily = NativeV5Tokens.Font)
                    }
                }
            }
        }
    }
}

}

@Composable
private fun V5DiscoverPage(
    candidates: List<CandidateCard>,
    stream: CandidateMediaSource,
    qaFixtureEnabled: Boolean,
    selectedCandidateId: String?,
    resetKey: Int,
    selectionRequestToken: Int,
    onStream: (CandidateMediaSource) -> Unit,
    onOpenCandidate: (String, Boolean) -> Unit,
    onAskAgent: (List<AgentContextReference>) -> Unit,
    trashedSessionIds: Set<String>,
    onTrashSessions: (Set<String>) -> Unit,
    onOpenSecondary: (V5Route, String, String) -> Unit,
    onToast: (String) -> Unit,
) {
    // A raw `candidate_*` envelope is an immutable PC evidence window.  It is
    // deliberately not a student-visible message: older installs may still
    // retain those envelopes locally, but only the PC-created `visit_*`
    // aggregate represents one video session in Discover.
    val records = candidates.filter {
        it.source == stream && it.id.value.startsWith("visit_")
    }
        .groupBy { it.visitId }
        .map { (_, windows) -> windows.maxBy { it.endPtsNs } }
        .sortedByDescending { it.endPtsNs }
        .take(12)
    val usePhonePrototype = qaFixtureEnabled && stream == CandidateMediaSource.PHONE_SCREEN && (records.isEmpty() || records.all { it.displayExcerpt.trim().length < 4 })
    // 第一视角尚未接入真实眼镜时，仍显示显式标注的演示会话；不能让用户
    // 在切换来源后落到“无记录”的死页面。
    val useGlassesPrototype = stream == CandidateMediaSource.GLASSES_FIRST_PERSON && records.isEmpty()
    var selectionMode by rememberSaveable { mutableStateOf(false) }
    var selectedIds by rememberSaveable { mutableStateOf(emptySet<String>()) }
    val scroll = rememberScrollState()
    LaunchedEffect(resetKey) { scroll.scrollTo(0) }
    LaunchedEffect(selectionRequestToken) {
        if (selectionRequestToken > 0) {
            selectionMode = true
            selectedIds = emptySet()
        }
    }
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scroll).padding(start = 16.dp, end = 16.dp, top = 52.dp, bottom = 18.dp),
    ) {
        V5PageHeading("发现", "", right = if (!selectionMode) "选择" else "取消") {
            selectionMode = !selectionMode
            if (!selectionMode) selectedIds = emptySet()
        }
        V5Segmented(
            items = listOf("手机屏幕流", "眼镜第一视角"),
            selected = if (stream == CandidateMediaSource.PHONE_SCREEN) 0 else 1,
        ) { onStream(if (it == 0) CandidateMediaSource.PHONE_SCREEN else CandidateMediaSource.GLASSES_FIRST_PERSON) }
        if (usePhonePrototype) {
            V5PhonePrototypeMessages.filterNot { it.id in trashedSessionIds }.forEach { item ->
                V5PrototypeMessageCard(item, selected = item.id in selectedIds, selectionMode = selectionMode) {
                    if (selectionMode) selectedIds = if (item.id in selectedIds) selectedIds - item.id else selectedIds + item.id
                    else onOpenCandidate(item.id, item.complete)
                }
            }
            if (V5PhoneSavedPrototypeMessage.id !in trashedSessionIds) V5PrototypeMessageCard(V5PhoneSavedPrototypeMessage, selected = V5PhoneSavedPrototypeMessage.id in selectedIds, selectionMode = selectionMode) {
                if (selectionMode) selectedIds = if (V5PhoneSavedPrototypeMessage.id in selectedIds) selectedIds - V5PhoneSavedPrototypeMessage.id else selectedIds + V5PhoneSavedPrototypeMessage.id
                else onOpenCandidate(V5PhoneSavedPrototypeMessage.id, V5PhoneSavedPrototypeMessage.complete)
            }
        } else if (useGlassesPrototype) {
            V5GlassesPrototypeMessages.filterNot { it.id in trashedSessionIds }.forEach { item ->
                V5PrototypeMessageCard(item, selected = item.id in selectedIds, selectionMode = selectionMode) {
                    if (selectionMode) selectedIds = if (item.id in selectedIds) selectedIds - item.id else selectedIds + item.id
                    else onOpenCandidate(item.id, item.complete)
                }
            }
        } else {
            // This is an empty-state canvas, not a capture-status bubble.
            // It is present only while the selected source has no session
            // messages, regardless of whether a transport is running or idle.
            if (records.isEmpty()) V5EmptyRecord(stream)
            records.filterNot { it.id.value in trashedSessionIds }.forEach { card ->
                val id = card.id.value
                V5MessageCard(
                    card = card,
                    selected = id in selectedIds,
                    selectionMode = selectionMode,
                    onClick = {
                        if (selectionMode) selectedIds = if (id in selectedIds) selectedIds - id else selectedIds + id
                        else onOpenCandidate(id, card.isL1Eligible)
                    },
                )
            }
        }
        if (selectionMode) {
            V5Panel(modifier = Modifier.padding(top = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("已选 ${selectedIds.size} 条", color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                }
                Row(modifier = Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    V5SecondaryButton("删除", modifier = Modifier.weight(1f)) {
                        if (selectedIds.isEmpty()) onToast("请先选择会话")
                        else { onTrashSessions(selectedIds); onToast("已将 ${selectedIds.size} 条会话移入回收站"); selectedIds = emptySet(); selectionMode = false }
                    }
                    V5PrimaryButton("问智能体", modifier = Modifier.weight(1f), enabled = selectedIds.isNotEmpty()) {
                        val references = V5DiscoverReferences(selectedIds, records, stream, qaFixtureEnabled)
                        if (references.isEmpty()) onToast("所选会话缺少可传递的证据引用") else onAskAgent(references)
                        selectedIds = emptySet()
                        selectionMode = false
                    }
                }
            }
        }
    }
}

@Composable
private fun V5PrototypeMessageCard(item: V5PrototypeMessage, selected: Boolean, selectionMode: Boolean, onClick: () -> Unit) {
    V5Panel(
        modifier = Modifier.padding(top = 8.dp).clickable(onClick = onClick),
        tint = if (selected) Color(0xFFF4FAFF) else Color.White,
        border = if (selected) Color(0xFF9FC4E9) else Color(0xFFE8EDF2),
        accent = if (item.complete) NativeV5Tokens.Accent else NativeV5Tokens.Warning,
    ) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(item.title, color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(item.summary, color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 3.dp), maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            V5Pill(item.status, item.complete)
        }
        Row(modifier = Modifier.fillMaxWidth().padding(top = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(item.meta, color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
            if (selectionMode) Text(if (selected) "已选" else "选择", color = NativeV5Tokens.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) else V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.Accent, contentDescription = "打开学习内容", modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun V5EmptyRecord(stream: CandidateMediaSource) {
    // Keep the blank canvas central and unframed.  This is intentionally not a
    // card/message: the first delivered session replaces it immediately.
    Box(
        modifier = Modifier.fillMaxWidth().height(420.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            V5LineIcon(
                V5Icon.DISCOVER,
                tint = NativeV5Tokens.IconMuted,
                contentDescription = if (stream == CandidateMediaSource.PHONE_SCREEN) "暂无手机屏幕流会话" else "暂无眼镜第一视角记录",
                modifier = Modifier.size(28.dp),
            )
            Text(
                if (stream == CandidateMediaSource.PHONE_SCREEN) "暂无手机屏幕流会话" else "暂无眼镜第一视角记录",
                color = NativeV5Tokens.Muted,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                fontFamily = NativeV5Tokens.Font,
                modifier = Modifier.padding(top = 10.dp),
            )
        }
    }
}

@Composable
private fun V5MessageCard(card: CandidateCard, selected: Boolean, selectionMode: Boolean, onClick: () -> Unit) {
    val complete = card.isL1Eligible
    V5Panel(
        modifier = Modifier.padding(top = 8.dp).clickable(onClick = onClick),
        tint = if (selected) Color(0xFFF4FAFF) else Color.White,
        border = if (selected) Color(0xFF9FC4E9) else Color(0xFFE8EDF2),
        accent = if (complete) NativeV5Tokens.Accent else NativeV5Tokens.Warning,
    ) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                // L0 is evidence only.  OCR/ASR fragments are retained behind
                // the evidence route and never promoted into a pseudo title or
                // a knowledge statement on the Discover list.
                Text("视频会话候选", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("已封存多模态证据，等待你的学习选择", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 3.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            V5Pill(if (complete) "L0 候选" else "仅记录", positive = complete)
        }
        Row(modifier = Modifier.fillMaxWidth().padding(top = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (card.source == CandidateMediaSource.PHONE_SCREEN) "手机屏幕流 · 会话级证据" else "眼镜第一视角 · 会话级证据", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (selectionMode) Text(if (selected) "已选" else "选择", color = NativeV5Tokens.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) else V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.Accent, contentDescription = "打开学习内容", modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun V5LearningDetail(
    candidate: CandidateCard?,
    displayTitle: String?,
    canOfferLearningLevels: Boolean,
    qaPreviewLevel: Int?,
    initialRequestedLevel: Int?,
    qaPreviewMapMode: Int,
    onBack: () -> Unit,
    onOpenCanvas: (Int) -> Unit,
    onOpenSecondary: (V5Route, String, String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pathStore = remember { MobileAppServices.learningPathStore(context) }
    val responseRecorder = remember { MobileAppServices.learningResponseRecorder(context) }
    val contentItems by remember { MobileAppServices.learningContentStore(context) }.observe().collectAsState(initial = emptyList())
    val learningPaths by pathStore.observe().collectAsState()
    // L1–L4 are rendered from a complete PC-delivered content package only.
    // Candidate evidence alone never unlocks a fabricated learning package.
    val contentItem = candidate?.let { card ->
        contentItems.lastOrNull { it.visitId == card.visitId && it.source == card.source }
    }
    val qaFixtureEnabled = qaPreviewLevel != null || displayTitle != null
    var prototypeLevel by rememberSaveable(candidate?.id?.value, displayTitle, qaPreviewLevel, initialRequestedLevel) {
        mutableStateOf(qaPreviewLevel ?: initialRequestedLevel ?: 0)
    }
    val persistedStage = contentItem?.let { learningPaths[it.content.contentId]?.stage }
    LaunchedEffect(initialRequestedLevel, contentItem?.content?.contentId) {
        if (initialRequestedLevel == 1 && contentItem != null) {
            pathStore.dispatchContent(contentItem.content.contentId, StudentLearningAction.OPEN_L1_CONCEPT_BRIEF)
        }
    }
    val level = persistedStage?.toV5Level() ?: prototypeLevel
    var mapMode by rememberSaveable(qaPreviewLevel, qaPreviewMapMode) { mutableStateOf(qaPreviewMapMode) }
    var reflection by rememberSaveable { mutableStateOf("") }
    var reflectionStatus by rememberSaveable(candidate?.id?.value, displayTitle) { mutableStateOf<String?>(null) }
    var evidenceExpanded by rememberSaveable { mutableStateOf(false) }
    var sourcesExpanded by rememberSaveable { mutableStateOf(false) }
    var practiceChoice by rememberSaveable { mutableStateOf<Int?>(null) }
    var blockedLevelRequest by rememberSaveable { mutableStateOf(false) }
    val title = contentItem?.content?.conceptTitle ?: displayTitle ?: candidate?.displayExcerpt?.take(30)?.takeIf { it.trim().length >= 4 }
        ?: if (qaFixtureEnabled) "生成式 AI 与数字媒体" else "等待学习内容包"
    val controlledPackageAvailable = contentItem != null || qaFixtureEnabled
    // Five levels have deliberately non-overlapping responsibilities.  Do not
    // leak maps, exercises, or free-text assessment into an earlier level.
    val levelTitle = listOf("L0 · 兴趣点候选", "L1 · 名词解释", "L2 · 知识脉络", "L3 · 客观练习", "L4 · 自主作答")[level]
    val qaFixtureLevelBody = if (displayTitle == "城市空间与建筑观察") listOf(
        "兴趣点候选：城市空间与建筑观察。该判断只对应当前时间锚点，尚未形成知识内容或学习结论。",
        "城市空间：人、建筑、道路、绿地等要素共同构成并被使用的场所环境。",
        "围绕“城市空间”梳理建筑尺度、道路、停留空间与绿地之间的关系。",
        "选择最能说明空间体验会被多因素共同影响的一个要素。",
        "用自己的话说明：这段第一视角观察中，哪个空间要素最值得继续记录，为什么？",
    )[level] else listOf(
        "兴趣点候选：生成式 AI 与数字媒体。仅保留当前候选、来源范围和时间窗口，不提供知识讲解。",
        "生成式 AI：利用数据学习模式，并生成文字、图像、声音或视频等新内容的技术。",
        "以概念关系组织背景、实例与可信材料，帮助比较生成式 AI、数字媒体与版权之间的联系。",
        "完成一道有明确正确答案和解析的客观题。",
        "用自己的话解释“生成式 AI 为什么会影响数字媒体创作中的版权讨论”。提交后进入评阅，不预先展示答案。",
    )[level]
    val levelBody = contentItem?.content?.let { content ->
        when (level) {
            0 -> "兴趣点候选：${content.conceptTitle}。只保留当前证据与来源范围，不在 L0 提供概念讲解。"
            1 -> content.conceptBrief
            2 -> content.background + "\n\n" + content.workedExample
            3 -> content.guidedPractice
            else -> content.selfPractice
        }
    } ?: if (qaFixtureEnabled) qaFixtureLevelBody else "当前候选尚未收到与同一 visit、同一来源证据绑定的 PC 学习内容包；仅可查看 L0 证据记录。"
    fun requestLevel(target: Int): Boolean {
        val action = when (target) {
            1 -> StudentLearningAction.OPEN_L1_CONCEPT_BRIEF
            2 -> StudentLearningAction.OPEN_L2_EXPLORATION
            3 -> StudentLearningAction.START_L3_GUIDED_PRACTICE
            4 -> StudentLearningAction.START_L4_SELF_PRACTICE
            else -> StudentLearningAction.VIEW_EVIDENCE
        }
        return if (contentItem != null) {
            pathStore.dispatchContent(contentItem.content.contentId, action)
        } else if (qaFixtureEnabled && canOfferLearningLevels) {
            // 仅在明确标注的演示会话中推进本地预览状态；不写入学习回执，
            // 也不把演示数据混入真实候选、画像或知识图谱。
            prototypeLevel = target
            true
        } else false
    }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 26.dp)) {
        V5BackButton("发现", onBack)
        Text(title, color = NativeV5Tokens.Ink, fontSize = 21.sp, lineHeight = 26.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 7.dp))
        Text("同一条内容的自愿学习路径；不会按观看时长自动升级。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 16.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 4.dp, bottom = 9.dp))
        V5Segmented(items = listOf("L0", "L1", "L2", "L3", "L4"), selected = level, compact = true) { requested ->
            if (requested == level) Unit
            else if (requested == 0) prototypeLevel = 0
            else if (!controlledPackageAvailable || !canOfferLearningLevels || !requestLevel(requested)) blockedLevelRequest = true
        }
        if (blockedLevelRequest) Text("当前记录尚无与该 visit 同源、完整的受控学习内容包，因此仅保留 L0，不开放 L1–L4。", color = NativeV5Tokens.Warning, fontSize = 10.sp, lineHeight = 15.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
        V5Panel(modifier = Modifier.padding(top = 15.dp)) {
            Text(levelTitle, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            Text(levelBody, color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 7.dp))
            if (level == 0) {
                V5SecondaryButton(if (evidenceExpanded) "收起捕获窗口与证据" else "查看捕获窗口与证据", Modifier.fillMaxWidth().padding(top = 8.dp)) { evidenceExpanded = !evidenceExpanded }
                V5SecondaryButton("查看证据明细", Modifier.fillMaxWidth()) { onOpenSecondary(V5Route.EVIDENCE, "捕获窗口与证据", title) }
                if (evidenceExpanded) Text("媒体 PTS、OCR、ASR、VLM 均必须来自同一 visit 和源哈希；原始媒体仅保存于本机受控范围。", color = NativeV5Tokens.Muted, fontSize = 10.sp, lineHeight = 15.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
            }
            if (level == 2) {
                if (sourcesExpanded) Text("数字媒体版权案例选读 · 生成式人工智能服务管理暂行办法 · 虚拟演员的技术与权利边界。正式版会绑定来源链接、版本和引用片段。", color = NativeV5Tokens.Muted, fontSize = 10.sp, lineHeight = 15.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
            }
        }
        if (level == 2) {
            V5ActionList(
                modifier = Modifier.padding(top = 10.dp),
                rows = listOf(
                    V5ActionListItem(
                        title = if (sourcesExpanded) "收起材料与实例" else "材料与实例",
                        detail = "案例、法规与阅读材料",
                        onClick = { sourcesExpanded = !sourcesExpanded },
                    ),
                    V5ActionListItem(
                        title = "来源列表",
                        detail = "版本、引用片段和访问范围",
                        onClick = { onOpenSecondary(V5Route.SOURCES, "材料与实例", title) },
                    ),
                ),
            )
        }
        // Only L2 visualizes a content map.  L0 is evidence-only; L1 is a
        // definition; L3 is an objectively marked question; L4 is free answer.
        if (level == 2 && controlledPackageAvailable) {
            V5Panel(modifier = Modifier.padding(top = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("概念关系", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                    TextButton(onClick = { onOpenCanvas(mapMode) }) { Text("全屏", color = NativeV5Tokens.Accent, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font) }
                }
                V5Segmented(items = listOf("思维导图", "知识图谱"), selected = mapMode) { mapMode = it }
                ContentConceptCanvas(
                    mapMode = mapMode,
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(204.dp),
                    onOpenNode = { label -> onOpenSecondary(V5Route.CONCEPT_DETAIL, "概念节点", label) },
                )
            }
        }
        if (level == 3) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("客观题", color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            Text("哪项描述最能说明本主题与版权讨论的关联？", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 16.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
            Row(modifier = Modifier.fillMaxWidth().padding(top = 7.dp), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                V5SecondaryButton("训练数据来源", Modifier.weight(1f)) { practiceChoice = 0 }
                V5SecondaryButton("观看时长", Modifier.weight(1f)) { practiceChoice = 1 }
            }
            practiceChoice?.let { chosen ->
                Text(
                    if (chosen == 0) "正确。训练数据来源会影响作品的权利边界与版权讨论。" else "不正确。观看时长不是本题所问的版权关联；请重试。",
                    color = if (chosen == 0) NativeV5Tokens.Positive else NativeV5Tokens.Warning,
                    fontSize = 10.sp,
                    lineHeight = 15.sp,
                    fontFamily = NativeV5Tokens.Font,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
        if (level == 4) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("自主作答", color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            Text("不提供标准答案。提交后记录为待评阅的学习回应。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 16.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
            OutlinedTextField(value = reflection, onValueChange = { reflection = it; reflectionStatus = null }, placeholder = { Text("用自己的话作答", fontSize = 11.sp) }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp), minLines = 3)
            V5PrimaryButton(if (reflectionStatus == "已提交，等待评阅") "已提交，等待评阅" else "提交并进入评阅", Modifier.fillMaxWidth().padding(top = 8.dp), enabled = reflection.isNotBlank() && contentItem != null) {
                val item = contentItem ?: return@V5PrimaryButton
                scope.launch {
                    reflectionStatus = runCatching {
                        responseRecorder.record(
                            StudentLearningResponse(
                                resultId = item.resultId,
                                contentId = item.content.contentId,
                                visitId = item.visitId,
                                source = item.source,
                                evidenceRefs = item.content.evidenceRefs,
                                stage = LearningStage.L4_SELF_PRACTICE,
                                body = reflection.trim(),
                                recordedAt = OffsetDateTime.now(),
                            ),
                        )
                        "已提交，等待评阅"
                    }.getOrElse { "当前内容包不满足提交条件" }
                }
            }
            reflectionStatus?.let { status -> Text(status, color = if (status.startsWith("已提交")) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp)) }
        }
        if (level < 4) V5PrimaryButton(
            label = listOf("查看 L1 概念小结", "继续探索 L2", "进入 L3 引导练习", "自愿进入 L4 自主表达")[level],
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
            enabled = controlledPackageAvailable && canOfferLearningLevels,
        ) { if (!requestLevel(level + 1)) blockedLevelRequest = true }
    }
}

private fun LearningStage.toV5Level(): Int = when (this) {
    LearningStage.L0_CANDIDATE -> 0
    LearningStage.L1_CONCEPT_BRIEF -> 1
    LearningStage.L2_EXPLORATION -> 2
    LearningStage.L3_GUIDED_PRACTICE -> 3
    LearningStage.L4_SELF_PRACTICE -> 4
}

@Composable
private fun V5AnalysisPage(
    candidates: List<CandidateCard>,
    profileView: V5ProfileView,
    chart: V5Chart,
    analysisFilterIndex: Int,
    onProfileView: (V5ProfileView) -> Unit,
    onChart: (V5Chart) -> Unit,
    onOpenCanvas: (String) -> Unit,
    onOpenSecondary: (V5Route, String, String) -> Unit,
    onSyncAiGraph: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 18.dp)) {
        V5PageHeading(if (profileView == V5ProfileView.KNOWLEDGE) "知识全览" else "学习分析", "") {}
        V5Segmented(items = listOf("知识全览", "学习分析"), selected = if (profileView == V5ProfileView.KNOWLEDGE) 0 else 1) { onProfileView(if (it == 0) V5ProfileView.KNOWLEDGE else V5ProfileView.STATS) }
        if (profileView == V5ProfileView.KNOWLEDGE) {
            V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("知识图谱", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                    TextButton(onClick = onSyncAiGraph, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 0.dp)) { Text("同步 AI 生成建议", color = NativeV5Tokens.Accent, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font) }
                    TextButton(onClick = { onOpenCanvas("knowledge") }) { Text("全屏", color = NativeV5Tokens.Accent, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font) }
                }
                V5GraphCanvas(
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(232.dp),
                    onOpenNode = { node -> onOpenSecondary(V5Route.NODE_DETAIL, "知识节点笔记", node.label) },
                    onCreateChild = { parent -> onOpenSecondary(V5Route.KNOWLEDGE_CREATE, "新建知识节点", parent?.label.orEmpty()) },
                )
            }
            V5ActionList(
                modifier = Modifier.padding(top = 10.dp),
                rows = listOf(
                    V5ActionListItem("学习证据 · ${candidates.size}", "筛选与证据索引") { onOpenSecondary(V5Route.FILTER, "学习证据", "知识全览") },
                    V5ActionListItem("图谱管理", "节点、关系与审核") { onOpenSecondary(V5Route.KNOWLEDGE_TOOLS, "图谱管理", "") },
                ),
            )
        } else {
            V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("统计视图", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("统计范围：${V5_ANALYSIS_FILTERS[analysisFilterIndex.coerceIn(V5_ANALYSIS_FILTERS.indices)]}", color = NativeV5Tokens.Muted, fontSize = 10.sp, lineHeight = 15.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 4.dp))
                Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(top = 9.dp)) {
                    V5Chart.entries.forEachIndexed { index, item -> TextButton(onClick = { onChart(item) }) { Text(item.label, color = if (item == chart) NativeV5Tokens.Accent else NativeV5Tokens.Muted, fontSize = 10.sp, fontWeight = if (item == chart) FontWeight.Bold else FontWeight.Medium, fontFamily = NativeV5Tokens.Font) } }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("当前图表：${chart.label}", color = NativeV5Tokens.Muted, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                    TextButton(onClick = { onOpenCanvas("stats:${chart.name}") }) { Text("全屏", color = NativeV5Tokens.Accent, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font) }
                }
                V5AnalyticsCanvas(chart, analysisFilterIndex, Modifier.fillMaxWidth().height(232.dp))
                Text("仅统计当前范围内已确认或已保存的知识来源与主动回执。", color = NativeV5Tokens.Muted, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
            }
            Row(modifier = Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                V5SecondaryButton("筛选", Modifier.weight(1f)) { onOpenSecondary(V5Route.FILTER, "筛选统计范围", chart.label) }
                V5SecondaryButton("查看来源证据", Modifier.weight(1f)) { onOpenSecondary(V5Route.PROFILE_EVIDENCE, "统计来源证据", chart.label) }
            }
        }
    }
}

@Composable
private fun V5AgentPage(
    libraryOpen: Boolean,
    sessionReferenceCount: Int,
    onLibrary: (Boolean) -> Unit,
    onOpenDiscoverSelection: () -> Unit,
) {
    val context = LocalContext.current
    val store = remember { MobileAppServices.agentWorkspaceStore(context) }
    val gateway = remember { MobileAppServices.pcAgentGatewayClient(context) }
    val directProvider = remember { MobileDirectAgentProviderStore(context) }
    val directClient = remember { MobileDirectAgentClient() }
    val workspace by store.observe().collectAsState(initial = cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot.empty())
    val scope = rememberCoroutineScope()
    var draft by rememberSaveable { mutableStateOf("") }
    var networkEnabled by rememberSaveable { mutableStateOf(true) }
    var gatewayStatusText by rememberSaveable { mutableStateOf("PC 智能体服务状态待读取") }
    val refreshGatewayStatus: () -> Unit = {
        scope.launch {
            gatewayStatusText = "正在检查 PC 智能体服务…"
            gatewayStatusText = runCatching { gateway.readStatus() }
                .fold(
                    onSuccess = { status ->
                        val target = listOfNotNull(status.provider, status.model).joinToString(" · ").ifBlank { "未配置模型" }
                        when (status.state) {
                            "READY" -> "PC 智能体已就绪：$target"
                            else -> "PC 智能体不可用：${status.errorMessage ?: status.errorCode ?: status.connectivity}"
                        }
                    },
                    onFailure = { error ->
                        if (error.message == "pc_agent_not_paired") "尚未配对 PC 智能体服务；请先在连接页完成受控配对。"
                        else "无法读取 PC 智能体状态：${error.message?.take(96) ?: "连接失败"}"
                    },
                )
        }
    }
    // 服务状态不占用对话工作台的固定高度。真实请求的可用性和失败原因
    // 由消息线程回显，避免把“状态说明”伪装成一张内容卡片。
    val submit: (AgentRequestMode) -> Unit = { mode ->
        val prompt = draft.trim()
        if (prompt.isNotEmpty()) {
            draft = ""
            scope.launch {
                store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.STUDENT, prompt, OffsetDateTime.now()))
                val configuredMode = directProvider.mode()
                val directConfig = directProvider.read()
                val useDirect = configuredMode == AgentExecutionMode.DIRECT_API ||
                    (configuredMode == AgentExecutionMode.AUTO && directConfig != null)
                val usePcGateway = configuredMode == AgentExecutionMode.PC_GATEWAY ||
                    (configuredMode == AgentExecutionMode.AUTO && directConfig == null && directProvider.autoFallbackAllowed())
                if (useDirect) {
                    if (directConfig == null) {
                        store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "手机直连尚未配置。请在服务页填写 HTTPS 地址、模型和 API Key。", OffsetDateTime.now()))
                    } else if (mode != AgentRequestMode.ANSWER) {
                        store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "当前直连服务仅已验证文本问答；联网、附件解析和文件生成需选择具备该能力的服务或 PC 网关。", OffsetDateTime.now()))
                    } else {
                        runCatching { directClient.answer(directConfig, prompt) }
                            .onSuccess { answer -> store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.ASSISTANT, answer, OffsetDateTime.now())) }
                            .onFailure { error -> store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "手机直连失败：${error.message?.take(160) ?: "网络请求失败"}", OffsetDateTime.now())) }
                    }
                } else if (usePcGateway) {
                    // A local URI must not be announced as usable context before
                    // the paired PC has received and checksum-accepted its bytes.
                    val preparedWorkspace = uploadQueuedResources(context, workspace, store, gateway)
                    runCatching { gateway.submit(mode, prompt, preparedWorkspace) }
                        .onSuccess { run ->
                            if (run.state == "SUCCEEDED" && !run.answer.isNullOrBlank()) {
                                store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.ASSISTANT, run.answer, OffsetDateTime.now(), run.runId))
                                run.artifact?.let { artifact ->
                                    runCatching { gateway.downloadArtifact(context, artifact) }
                                        .onSuccess { store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "文件已保存到下载目录：${artifact.displayName}", OffsetDateTime.now())) }
                                        .onFailure { error -> store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "文件已生成但下载失败：${error.message?.take(160) ?: "未知错误"}", OffsetDateTime.now())) }
                                }
                            } else {
                                store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "本次请求未完成：${run.errorMessage ?: run.errorCode ?: "PC 智能体未返回结果"}", OffsetDateTime.now()))
                            }
                        }
                        .onFailure { error -> store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "无法连接已配对 PC：${error.message?.take(160) ?: "网络请求失败"}", OffsetDateTime.now())) }
                } else {
                    store.appendMessage(AgentConversationMessage(UUID.randomUUID().toString(), AgentMessageAuthor.SYSTEM, "自动模式未配置手机直连，且未允许切换到 PC 网关。请在服务页选择执行方式。", OffsetDateTime.now()))
                }
            }
        }
    }
    Column(modifier = Modifier.fillMaxSize().padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(if (libraryOpen) "资料库" else "智能体", color = NativeV5Tokens.Ink, fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
            if (!libraryOpen) TextButton(onClick = { scope.launch { store.beginEmptyConversation() } }, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 7.dp, vertical = 0.dp)) { Text("新对话", color = NativeV5Tokens.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) }
            TextButton(onClick = { onLibrary(!libraryOpen) }, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 7.dp, vertical = 0.dp)) { Text(if (libraryOpen) "对话" else "资料库", color = NativeV5Tokens.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) }
        }
        if (libraryOpen) {
            V5LibraryPage(Modifier.fillMaxSize().padding(top = 8.dp), sessionReferenceCount = sessionReferenceCount, store = store, onOpenDiscoverSelection = onOpenDiscoverSelection)
        } else {
            // 只有消息线程滚动；Composer 属于最外层网格的最后一行，不能因
            // 页面滚动或系统导航栏高度而上浮。
            Column(modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(top = 6.dp, bottom = 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                // 与网页最终工作台一致：空会话也从一条助手消息开始，不能用
                // 大号说明卡替代聊天线程。
                if (workspace.messages.isEmpty()) V5ChatBubble("你好，想做什么？", fromStudent = false)
                workspace.messages.forEach { message -> V5ChatBubble(message.body, fromStudent = message.author == AgentMessageAuthor.STUDENT) }
            }
            Surface(shape = RoundedCornerShape(14.dp), color = Color(0xF7FFFFFF), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFD5E2EE)), shadowElevation = 1.dp) {
                Column(Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
                    // 对话输入保持整行宽度；附件和联网切换属于输入工具栏，不能
                    // 挤压文本区导致中文占位提示断裂成两行。
                    BasicTextField(
                        value = draft,
                        onValueChange = { draft = it },
                        modifier = Modifier.fillMaxWidth().height(38.dp),
                        singleLine = false,
                        maxLines = 2,
                        textStyle = TextStyle(color = NativeV5Tokens.Ink, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font),
                        decorationBox = { inner ->
                            Box(Modifier.fillMaxSize().padding(horizontal = 4.dp, vertical = 5.dp)) {
                                if (draft.isBlank()) Text("输入问题，或描述需要生成的文件…", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font)
                                inner()
                            }
                        },
                    )
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        V5IconAction(V5Icon.ATTACH, "打开资料库", { onLibrary(true) })
                        V5IconAction(V5Icon.NETWORK, if (networkEnabled) "关闭联网检索" else "开启联网检索", { networkEnabled = !networkEnabled }, active = networkEnabled)
                        Spacer(Modifier.weight(1f))
                        V5IconAction(V5Icon.SEND, "发送", {
                            submit(agentRequestModeForDraft(draft, networkEnabled))
                        }, enabled = draft.isNotBlank(), primary = true)
                    }
                }
            }
        }
    }
}

@Composable
private fun V5AgentServicePage(onBack: () -> Unit, onOpenConnection: () -> Unit) {
    val context = LocalContext.current
    val gateway = remember { MobileAppServices.pcAgentGatewayClient(context) }
    val directProvider = remember { MobileDirectAgentProviderStore(context) }
    val directClient = remember { MobileDirectAgentClient() }
    val scope = rememberCoroutineScope()
    var executionMode by rememberSaveable { mutableStateOf(directProvider.mode()) }
    var allowFallback by rememberSaveable { mutableStateOf(directProvider.autoFallbackAllowed()) }
    var baseUrl by rememberSaveable { mutableStateOf(directProvider.read()?.baseUrl.orEmpty()) }
    var model by rememberSaveable { mutableStateOf(directProvider.read()?.model.orEmpty()) }
    var apiKey by rememberSaveable { mutableStateOf("") }
    var directStatus by rememberSaveable { mutableStateOf(if (directProvider.read() == null) "未配置" else "已保存") }
    var checking by rememberSaveable { mutableStateOf(false) }
    var state by rememberSaveable { mutableStateOf("尚未读取") }
    var provider by rememberSaveable { mutableStateOf("未配置") }
    var detail by rememberSaveable { mutableStateOf("连接已配对的 PC 后读取模型与检索服务状态。") }
    val refresh = {
        scope.launch {
            checking = true
            runCatching { gateway.readStatus() }
                .onSuccess { status ->
                    state = if (status.state == "READY") "可用" else "不可用"
                    provider = listOfNotNull(status.provider, status.model).joinToString(" · ").ifBlank { "未配置" }
                    detail = status.errorMessage ?: status.errorCode ?: status.connectivity
                }
                .onFailure { error ->
                    state = "未连接"
                    provider = "未读取"
                    detail = if (error.message == "pc_agent_not_paired") "尚未完成 PC 安全配对。" else "无法读取 PC 服务：${error.message?.take(100) ?: "连接失败"}"
                }
            checking = false
        }
    }
    LaunchedEffect(Unit) { refresh() }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 20.dp)) {
        V5BackButton("设置", onBack)
        V5PageHeading("服务配置", "") {}
        V5Panel(modifier = Modifier.padding(top = 8.dp)) {
            Text("执行方式", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            V5Segmented(listOf("手机直连", "PC 网关", "自动"), executionMode.ordinal, compact = true) { index ->
                executionMode = AgentExecutionMode.entries[index]
                directProvider.setMode(executionMode)
            }
            if (executionMode == AgentExecutionMode.AUTO) {
                V5ToggleRow("允许降级", "", allowFallback) {
                    allowFallback = it
                    directProvider.setAutoFallbackAllowed(it)
                }
            }
        }
        if (executionMode != AgentExecutionMode.PC_GATEWAY) V5Panel(modifier = Modifier.padding(top = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("手机直连 API", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                V5Pill(directStatus.take(10), directStatus == "已保存" || directStatus.startsWith("连接成功"))
            }
            V5CompactConfigInput("地址", baseUrl, "https://api.example.com/v1", { baseUrl = it })
            V5CompactConfigInput("模型", model, "模型名称", { model = it })
            V5CompactConfigInput("密钥", apiKey, if (directProvider.read() == null) "首次保存必须填写" else "留空保留已有密钥", { apiKey = it })
            Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                V5SecondaryButton("删除", Modifier.weight(1f)) {
                    directProvider.clear(); apiKey = ""; directStatus = "未配置"
                }
                V5PrimaryButton("保存", Modifier.weight(1f)) {
                    runCatching {
                        val existing = directProvider.read()
                        directProvider.save(baseUrl, model, apiKey.ifBlank { existing?.apiKey.orEmpty() })
                    }.onSuccess { apiKey = ""; directStatus = "已保存" }
                        .onFailure { directStatus = it.message?.take(36) ?: "保存失败" }
                }
                V5SecondaryButton("测试", Modifier.weight(1f), enabled = !checking) {
                    val config = directProvider.read()
                    if (config == null) directStatus = "请先保存完整配置" else scope.launch {
                        checking = true
                        directStatus = runCatching { directClient.test(config) }.getOrElse { "连接失败：${it.message?.take(28) ?: "未知错误"}" }
                        checking = false
                    }
                }
            }
        }
        if (executionMode != AgentExecutionMode.DIRECT_API) V5Panel(modifier = Modifier.padding(top = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("PC 网关", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                Text(state, color = if (state == "可用") NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            }
            Text(provider, color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Row(modifier = Modifier.fillMaxWidth().padding(top = 5.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                V5SecondaryButton(if (checking) "检测中" else "刷新", Modifier.weight(1f), enabled = !checking) { refresh() }
                V5SecondaryButton("配对", Modifier.weight(1f), onClick = onOpenConnection)
            }
        }
    }
}

/** Files are generated by the paired PC only; this merely selects its declared export contract. */
private fun agentRequestModeForDraft(draft: String, networkEnabled: Boolean): AgentRequestMode {
    val normalized = draft.lowercase()
    return when {
        listOf("pptx", "ppt", "幻灯片", "演示文稿").any(normalized::contains) -> AgentRequestMode.EXPORT_PPTX
        listOf("docx", "word", "文档").any(normalized::contains) -> AgentRequestMode.EXPORT_DOCX
        listOf("pdf", "便携文档").any(normalized::contains) -> AgentRequestMode.EXPORT_PDF
        listOf("生成文件", "导出", "markdown", "md").any(normalized::contains) -> AgentRequestMode.EXPORT_MARKDOWN
        networkEnabled -> AgentRequestMode.WEB_SEARCH
        else -> AgentRequestMode.ANSWER
    }
}

@Composable
private fun V5LibraryPage(
    modifier: Modifier = Modifier,
    sessionReferenceCount: Int,
    store: AndroidAgentWorkspaceStore,
    onOpenDiscoverSelection: () -> Unit,
) {
    val context = LocalContext.current
    val workspace by store.observe().collectAsState(initial = cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot.empty())
    val graph by remember { MobileAppServices.knowledgeVault(context) }.observeGraph().collectAsState(initial = cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot.empty())
    val scope = rememberCoroutineScope()
    var tab by rememberSaveable { mutableStateOf(0) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        val additions = uris.mapNotNull(context::toLocalAttachment)
        if (additions.isNotEmpty()) scope.launch { store.addResources(additions) }
    }
    Column(modifier = modifier.verticalScroll(rememberScrollState())) {
        V5LibraryTabBar(selected = tab, onSelect = { tab = it })
        if (tab == 0) V5UploadWell(modifier = Modifier.padding(top = 8.dp)) {
            picker.launch(arrayOf("application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "text/csv", "image/*", "audio/*", "video/*"))
        }
        V5Panel(modifier = Modifier.padding(top = 8.dp)) {
            when (tab) {
                0 -> {
                    Text(if (workspace.resources.isEmpty()) "尚未添加资料" else "${workspace.resources.size} 个资料", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font)
                    workspace.resources.forEach { resource -> V5SecondaryButton("移除 ${resource.displayName}", Modifier.fillMaxWidth()) { scope.launch { store.removeResource(resource.id) } } }
                }
                1 -> {
                    Text(if (workspace.contextReferences.isEmpty() && sessionReferenceCount == 0) "尚未选择会话" else "${workspace.contextReferences.size.coerceAtLeast(sessionReferenceCount)} 条会话", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font)
                    workspace.contextReferences.forEach { reference -> V5SecondaryButton("移除 ${reference.title}", Modifier.fillMaxWidth()) { scope.launch { store.replaceContextReferences(workspace.contextReferences.filterNot { it.id == reference.id }) } } }
                    V5SecondaryButton("选择会话", Modifier.fillMaxWidth()) { onOpenDiscoverSelection() }
                }
                else -> {
                    if (graph.nodes.isEmpty()) {
                        Text("暂无知识节点", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font)
                    } else {
                        graph.nodes.take(12).forEach { node ->
                            val referenceId = "knowledge:${node.id.value}"
                            val referenced = workspace.knowledgeReferences.any { it.id == referenceId }
                            V5SecondaryButton(if (referenced) "移除 ${node.label}" else "引用 ${node.label}", Modifier.fillMaxWidth()) {
                                scope.launch {
                                    val next = if (referenced) workspace.knowledgeReferences.filterNot { it.id == referenceId } else workspace.knowledgeReferences + AgentKnowledgeReference(referenceId, node.label, node.note, node.evidenceRefs)
                                    store.replaceKnowledgeReferences(next)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V5LibraryTabBar(selected: Int, onSelect: (Int) -> Unit) {
    val labels = listOf("文件与资料", "发现会话", "知识库")
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(top = 3.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        labels.forEachIndexed { index, label ->
            val active = index == selected
            Surface(
                modifier = Modifier.clickable { onSelect(index) },
                shape = RoundedCornerShape(10.dp),
                color = if (active) Color(0xFFECF6FF) else Color(0xFFF8FAFC),
                border = androidx.compose.foundation.BorderStroke(1.dp, if (active) Color(0xFFB9D4EF) else Color(0xFFDCE4EC)),
            ) {
                Text(label, color = if (active) Color(0xFF116BBF) else NativeV5Tokens.Muted, fontSize = 11.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp))
            }
        }
    }
}

@Composable
private fun V5UploadWell(modifier: Modifier = Modifier, onPick: () -> Unit) {
    Surface(modifier = modifier.fillMaxWidth().clickable(onClick = onPick), shape = RoundedCornerShape(16.dp), color = Color(0xFFF7FBFF), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFB9CFE1))) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("添加本地资料", color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            V5PrimaryButton("选择文件", Modifier.fillMaxWidth().padding(top = 7.dp), onClick = onPick)
        }
    }
}

/**
 * V5 replaces the upstream stream tab, so it must also retain the upstream
 * module-lifecycle responsibility.  Resolving a facade alone leaves
 * [RtspStreamingModule]'s initial state permanently `isBusy=true`; the old
 * screen tab normally activated it through [StreamingModuleManager].
 *
 * This starts only the existing RTSP module while the user is in a foreground
 * V5 surface.  It does not start MediaProjection or capture media: those still
 * require the explicit button path and Android's consent dialog.
 */
@Composable
private fun rememberStartedRtspFacade(): RtspTransportFacade? {
    val context = LocalContext.current
    val moduleManager = remember {
        runCatching { GlobalContext.get().get<StreamingModuleManager>() }.getOrNull()
    }
    val facade = remember {
        runCatching { GlobalContext.get().get<RtspTransportFacade>() }.getOrNull()
    }
    LaunchedEffect(moduleManager) {
        moduleManager?.let { manager ->
            runCatching {
                manager.startModule(RtspStreamingModule.Id, context.applicationContext)
            }
        }
    }
    return facade
}

@Composable
private fun V5ConnectionPage(pcPaired: Boolean, onOpenControls: () -> Unit, onOpenSecondary: (V5Route, String, String) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pcDelivery = remember { MobileAppServices.pcDeliveryClient(context) }
    val pcLinkStore = remember { MobileAppServices.pcLinkStore(context) }
    var paired by rememberSaveable { mutableStateOf(pcPaired || pcLinkStore.read() != null) }
    var pairingDialogOpen by rememberSaveable { mutableStateOf(false) }
    var pairingAddress by rememberSaveable { mutableStateOf("") }
    var pairingCode by rememberSaveable { mutableStateOf("") }
    var pairingStatus by rememberSaveable { mutableStateOf<String?>(null) }
    var discoveredCandidates by remember { mutableStateOf<List<LanGatewayCandidate>>(emptyList()) }
    var discoveryDialogOpen by rememberSaveable { mutableStateOf(false) }
    var discoveryInProgress by rememberSaveable { mutableStateOf(false) }
    var activePcCaptureSessionId by rememberSaveable { mutableStateOf<String?>(null) }
    var pcCaptureStatus by rememberSaveable { mutableStateOf<String?>(null) }
    val lanDiscovery = remember { LanGatewayDiscovery() }
    val facade = rememberStartedRtspFacade()
    val fallback = remember { MutableStateFlow(RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null)) }
    val transport by (facade?.state ?: fallback).collectAsState()
    val streaming = transport.status == RtspTransportStatus.STREAMING || transport.status == RtspTransportStatus.STREAMING_NO_CONSUMER
    val rtspSettings = remember { runCatching { GlobalContext.get().get<RtspSettings>() }.getOrNull() }
    val rtspFallback = remember { MutableStateFlow(RtspSettings.Data()) }
    val currentRtspSettings by (rtspSettings?.data ?: rtspFallback).collectAsState()
    val captureRequester = rememberScreenCaptureStartRequester()
    ScreenCapturePermissionFlow(
        startRequester = captureRequester,
        permissionScopeKey = "rtsp",
        // startAttemptId is the service's explicit permission-pending fact.
        // Do not derive it again from a presentation status: a retained error
        // from a previous client attempt used to mask WAITING state and stop
        // Android's MediaProjection dialog from ever launching.
        startAttemptId = transport.startAttemptId,
        onStartRequested = { educationShown -> facade?.beginUserCapture(context, educationShown) },
        onPermissionGranted = { attemptId, permissionIntent -> facade?.submitProjectionPermission(attemptId, permissionIntent) },
        onPermissionDenied = { attemptId -> facade?.rejectProjectionPermission(attemptId) },
    )
    // This is the application-level hand-off missing from the former flow:
    // MediaProjection -> Android RTSP SERVER -> authenticated PC supervisor.
    // It runs only after STREAMING is factual, never merely after tapping 开始.
    LaunchedEffect(streaming, paired, currentRtspSettings.mode, currentRtspSettings.serverPort, currentRtspSettings.serverPath) {
        if (streaming && paired && currentRtspSettings.mode == RtspSettings.Values.Mode.SERVER && activePcCaptureSessionId == null) {
            val sessionId = "phone-" + UUID.randomUUID()
            pcCaptureStatus = "正在通知 PC 捕获屏幕流…"
            runCatching { pcDelivery.startCaptureSession(sessionId, currentRtspSettings.serverPort, currentRtspSettings.serverPath) }
                .onSuccess { session ->
                    activePcCaptureSessionId = session.sessionId
                    pcCaptureStatus = when (session.state) {
                        "RUNNING" -> "PC 已接收，正在分析"
                        "STARTING" -> "PC 已接收，正在启动分析"
                        else -> "PC 分析未启动：${session.error ?: session.state}"
                    }
                }
                .onFailure { error -> pcCaptureStatus = "PC 捕获未启动：${error.message?.take(100) ?: "连接失败"}" }
        } else if (!streaming && activePcCaptureSessionId != null) {
            val sessionId = activePcCaptureSessionId ?: return@LaunchedEffect
            runCatching { pcDelivery.stopCaptureSession(sessionId) }
            activePcCaptureSessionId = null
            pcCaptureStatus = "手机流已停止，PC 正在收尾当前证据窗口"
        } else if (streaming && currentRtspSettings.mode != RtspSettings.Values.Mode.SERVER) {
            pcCaptureStatus = "PC 自动分析要求“服务端”模式；当前客户端模式没有 PC 接收端"
        }
    }
    LaunchedEffect(paired) {
        if (paired) PcSyncForegroundService.start(context.applicationContext)
    }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 18.dp)) {
        V5PageHeading("连接", "") {}
        // 连接首页只保留一个公开媒体会话区块：主控制 + 设置入口。
        // “会话详情”属于媒体会话设置内部状态，不再作为第二条平行入口。
        V5Panel(modifier = Modifier.padding(top = 8.dp), tint = Color(0xFFF5FAFF), border = Color(0xFFDCEAF7)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("手机屏幕流", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                V5Pill(if (streaming) "传输中" else "未开始", streaming)
            }
            Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (streaming) {
                    V5PrimaryButton("停止", Modifier.weight(1f), enabled = facade != null) { facade?.stopUserCapture() }
                } else {
                    V5PrimaryButton("开始", Modifier.weight(1f), enabled = facade != null && transport.status != RtspTransportStatus.STARTING) { captureRequester.request() }
                }
                V5SecondaryButton("会话设置", Modifier.weight(1f)) { onOpenControls() }
            }
            when {
                facade == null -> Text("传输内核未就绪", color = NativeV5Tokens.Warning, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 4.dp))
                transport.failureCode != null -> Text("启动失败：${transport.failureCode}", color = NativeV5Tokens.Warning, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 4.dp))
            }
            pcCaptureStatus?.let { Text(it, color = if (it.startsWith("PC 已接收") || it.startsWith("手机流已停止")) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 3.dp)) }
        }
        V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("本地 PC 中枢", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                V5Pill(if (paired) "已配对" else "待配对", paired)
                if (paired) TextButton(onClick = { scope.launch { pcDelivery.unpair(); paired = false; pairingStatus = "PC 配对已解除" } }, contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 7.dp, end = 0.dp, top = 0.dp, bottom = 0.dp)) { Text("解除", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font) }
            }
            Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (paired) {
                    V5SecondaryButton("同步", Modifier.weight(1f)) {
                        scope.launch {
                            pairingStatus = "正在同步…"
                            pairingStatus = runCatching { pcDelivery.synchronizeOnce() }.fold(
                                onSuccess = { count -> "已同步 $count 项结果" },
                                onFailure = { error -> "PC 同步失败：${error.message?.take(120) ?: "连接失败"}" },
                            )
                        }
                    }
                    V5SecondaryButton("回传记录", Modifier.weight(1f)) { onOpenSecondary(V5Route.PC_DETAIL, "PC 中枢回传", "候选、学习回应和图谱事件") }
                } else {
                    V5PrimaryButton("发现 PC", Modifier.weight(1f)) {
                        scope.launch {
                            discoveryInProgress = true
                            pairingStatus = "正在发现附近 PC…"
                            discoveredCandidates = runCatching { lanDiscovery.discover() }.getOrElse { emptyList() }
                            discoveryInProgress = false
                            if (discoveredCandidates.isEmpty()) {
                                pairingStatus = "未发现可配对 PC；请确认 PC 网关已开启附近配对"
                            } else {
                                discoveryDialogOpen = true
                                pairingStatus = null
                            }
                        }
                    }
                    V5SecondaryButton("回传记录", Modifier.weight(1f)) { onOpenSecondary(V5Route.PC_DETAIL, "PC 中枢回传", "候选、学习回应和图谱事件") }
                }
            }
            if (!paired) TextButton(onClick = { pairingDialogOpen = true }, enabled = !discoveryInProgress, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) { Text("手动添加 PC", color = NativeV5Tokens.Muted, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font) }
            pairingStatus?.let { Text(it, color = if (it.startsWith("配对完成") || it.startsWith("已同步") || it.startsWith("PC 配对已解除")) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp)) }
        }
        V5Panel(modifier = Modifier.padding(top = 8.dp), contentPadding = 0.dp) {
            listOf("眼镜 / EEG" to "本地封存", "手表" to "状态流").forEachIndexed { index, (title, detail) ->
                Column(Modifier.fillMaxWidth().clickable { onOpenSecondary(V5Route.DEVICE_DETAIL, "设备连接", title) }.padding(horizontal = 12.dp, vertical = 9.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(title, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                        V5Pill("未接入", false)
                        V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.IconMuted, contentDescription = "打开$title 设备详情", modifier = Modifier.size(18.dp))
                    }
                    Text(detail, color = NativeV5Tokens.Muted, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 1.dp))
                }
                if (index == 0) Spacer(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFFE8EDF2)))
            }
        }
    }
    if (pairingDialogOpen) AlertDialog(
        onDismissRequest = { pairingDialogOpen = false },
        title = { Text("配置 PC 安全配对", fontFamily = NativeV5Tokens.Font) },
        text = {
            Column {
                OutlinedTextField(value = pairingAddress, onValueChange = { pairingAddress = it }, label = { Text("PC 配对地址", fontFamily = NativeV5Tokens.Font) }, placeholder = { Text("https://PC:8443#spki=sha256/...", fontFamily = NativeV5Tokens.Font) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                OutlinedTextField(value = pairingCode, onValueChange = { pairingCode = it }, label = { Text("一次性配对码", fontFamily = NativeV5Tokens.Font) }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true)
            }
        },
        confirmButton = { TextButton(enabled = pairingAddress.isNotBlank() && pairingCode.isNotBlank(), onClick = { scope.launch { pairingStatus = "正在验证 HTTPS 证书与 SPKI 指纹…"; runCatching { pcDelivery.pair(pairingAddress, pairingCode) }.onSuccess { paired = true; PcSyncForegroundService.start(context.applicationContext); pairingCode = ""; pairingDialogOpen = false; pairingStatus = "配对完成：PC 网关令牌已安全保存" }.onFailure { error -> pairingStatus = "PC 配对失败：${error.message?.take(120) ?: "连接失败"}" } } }) { Text("开始配对", fontFamily = NativeV5Tokens.Font) } },
        dismissButton = { TextButton(onClick = { pairingCode = ""; pairingDialogOpen = false }) { Text("取消", fontFamily = NativeV5Tokens.Font) } },
    )
    if (discoveryDialogOpen) AlertDialog(
        onDismissRequest = { discoveryDialogOpen = false },
        title = { Text("发现附近 PC", fontFamily = NativeV5Tokens.Font) },
        text = {
            Column {
                discoveredCandidates.forEach { candidate ->
                    TextButton(onClick = {
                        scope.launch {
                            pairingStatus = "正在验证 ${candidate.deviceName} 的证书…"
                            runCatching { pcDelivery.pairDiscovered(candidate) }
                                .onSuccess { paired = true; PcSyncForegroundService.start(context.applicationContext); discoveryDialogOpen = false; pairingStatus = "配对完成：后续将自动重连" }
                                .onFailure { error -> pairingStatus = "PC 配对失败：${error.message?.take(120) ?: "连接失败"}" }
                        }
                    }, modifier = Modifier.fillMaxWidth()) {
                        Text("信任并配对 · ${candidate.deviceName}", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                        V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.IconMuted, contentDescription = "信任并配对 ${candidate.deviceName}", modifier = Modifier.size(18.dp))
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { discoveryDialogOpen = false }) { Text("取消", fontFamily = NativeV5Tokens.Font) } },
    )
}

@Composable
private fun V5FullKnowledgeCanvas(
    title: String,
    kind: String,
    analysisFilterIndex: Int,
    onBack: () -> Unit,
    onOpenContentNode: (String) -> Unit,
    onOpenKnowledgeNode: (KnowledgeGraphNode) -> Unit,
    onCreateKnowledgeChild: (KnowledgeGraphNode?) -> Unit,
) {
    val contentMode = kind.substringAfter("content:", "0").toIntOrNull()?.coerceIn(0, 1) ?: 0
    val isContent = kind.startsWith("content")
    val statisticsChart = kind.substringAfter("stats:", "").let { name -> V5Chart.entries.firstOrNull { it.name == name } }
    Column(modifier = Modifier.fillMaxSize().padding(top = 58.dp)) {
        V5BackButton(if (isContent) "L2 探究" else if (statisticsChart != null) "学习分析" else "知识全览", onBack, Modifier.padding(horizontal = 16.dp))
        Text(title, color = NativeV5Tokens.Ink, fontSize = 21.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(horizontal = 16.dp))
        Text(if (isContent) "拖动节点调整布局；单击节点查看当前内容的概念说明。" else if (statisticsChart != null) "全屏查看当前统计图；统计始终可回到来源证据，不解释人格、能力或心理状态。" else "拖动节点调整布局；单击节点进入编辑；右缘小＋建立子节点。", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        if (isContent) {
            ContentConceptCanvas(mapMode = contentMode, modifier = Modifier.fillMaxWidth().weight(1f).padding(16.dp), expanded = true, onOpenNode = onOpenContentNode)
        } else if (statisticsChart != null) {
            V5AnalyticsCanvas(statisticsChart, analysisFilterIndex, Modifier.fillMaxWidth().weight(1f).padding(16.dp))
        } else {
            V5GraphCanvas(
                modifier = Modifier.fillMaxWidth().weight(1f).padding(16.dp),
                expanded = true,
                onOpenNode = onOpenKnowledgeNode,
                onCreateChild = onCreateKnowledgeChild,
            )
        }
    }
}

@Composable
private fun V5SettingsDrawer(onDismiss: () -> Unit, onOpenSettings: (String) -> Unit, onOpenConnection: () -> Unit) {
    Box(Modifier.fillMaxSize().background(Color(0x55202A35)).clickable(onClick = onDismiss)) {
        // nova 8 is a 360dp logical canvas. 236dp keeps roughly one third of
        // the page reachable for the explicit outside-tap dismissal gesture.
        Surface(modifier = Modifier.fillMaxHeight().width(236.dp).clickable(enabled = false) {}, shape = RoundedCornerShape(topEnd = 18.dp, bottomEnd = 18.dp), color = Color(0xF7F8FCFF), shadowElevation = 8.dp) {
            Column(Modifier.padding(horizontal = 12.dp, vertical = 20.dp)) {
                Text("设置", color = NativeV5Tokens.Ink, fontSize = 23.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font)
                V5Panel(tint = Color.White, border = Color(0xFFF0F2F5), contentPadding = 0.dp, modifier = Modifier.padding(top = 10.dp)) {
                    listOf("显示", "通知", "智能体与服务", "公开媒体会话", "视频", "音频", "网络", "隐私与数据").forEach { title ->
                        TextButton(onClick = { onOpenSettings(title) }, modifier = Modifier.fillMaxWidth().height(44.dp)) { Text(title, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f)); V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.IconMuted, contentDescription = "打开$title 设置", modifier = Modifier.size(17.dp)) }
                    }
                }
                TextButton(onClick = onOpenConnection, modifier = Modifier.padding(top = 4.dp)) { Text("打开连接与设备", color = NativeV5Tokens.Accent, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font) }
            }
        }
    }
}

@Composable
private fun V5SettingsPage(
    initialSection: String?,
    onBack: () -> Unit,
    onReturnToDrawer: () -> Unit,
    onOpenMediaSession: (String) -> Unit,
    onOpenSecondary: (V5Route, String, String) -> Unit,
    textScaleMultiplier: Float,
    onTextScaleMultiplier: (Float) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val appSettings = remember { runCatching { GlobalContext.get().get<AppSettings>() }.getOrNull() }
    val appFallback = remember { MutableStateFlow(AppSettings.Data()) }
    val appData by (appSettings?.data ?: appFallback).collectAsState()
    val section = initialSection
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 26.dp)) {
        TextButton(onClick = { if (section == null) onBack() else onReturnToDrawer() }, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) { Text(if (section == null) "‹ 返回" else "‹ 设置", color = NativeV5Tokens.Accent, fontSize = 14.sp, fontFamily = NativeV5Tokens.Font) }
        if (section == null) return@Column
        V5PageHeading(section, "") {}
        when (section) {
            "显示" -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("显示与阅读", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                V5Segmented(listOf("紧凑", "标准", "放大"), when { textScaleMultiplier < 0.97F -> 0; textScaleMultiplier < 1.08F -> 1; else -> 2 }) { onTextScaleMultiplier(listOf(0.94F, 1.00F, 1.15F)[it]) }
                Text("外观", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 14.dp))
                V5Segmented(listOf("浅色", "深色", "跟随系统"), when (appData.nightMode) { AppCompatDelegate.MODE_NIGHT_NO -> 0; AppCompatDelegate.MODE_NIGHT_YES -> 1; else -> 2 }) { selected ->
                    val mode = listOf(AppCompatDelegate.MODE_NIGHT_NO, AppCompatDelegate.MODE_NIGHT_YES, AppCompatDelegate.MODE_NIGHT_UNSPECIFIED)[selected]
                    appSettings?.let { settings -> scope.launch { settings.updateData { copy(nightMode = mode) } } }
                }
                V5ToggleRow("动态主题", "跟随设备支持情况生成系统色彩。", appData.dynamicTheme, enabled = appSettings != null) { value -> appSettings?.let { settings -> scope.launch { settings.updateData { copy(dynamicTheme = value) } } } }
            }
            "通知" -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("通知", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                V5SecondaryButton("通知历史", Modifier.fillMaxWidth().padding(top = 5.dp)) { onOpenSecondary(V5Route.NOTICE_HISTORY, "通知历史", "顶部横幅与免打扰记录") }
            }
            "隐私与数据" -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("隐私与数据", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                V5SecondaryButton("导出本地数据", Modifier.fillMaxWidth().padding(top = 5.dp)) { onOpenSecondary(V5Route.EXPORT, "本地数据导出", "导出前可审核范围") }
                V5SecondaryButton("删除审计记录", Modifier.fillMaxWidth()) { onOpenSecondary(V5Route.AUDIT, "删除审计", "本地事件与删除记录") }
            }
            else -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("媒体会话设置", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                V5PrimaryButton("打开${section}设置", Modifier.fillMaxWidth().padding(top = 5.dp)) { onOpenMediaSession(section) }
            }
        }
    }
}

@Composable
private fun V5MediaControlsPage(section: String?, onBack: () -> Unit) {
    val facade = rememberStartedRtspFacade()
    val fallback = remember { MutableStateFlow(RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null)) }
    val transport by (facade?.state ?: fallback).collectAsState()
    val rtspSettings = remember { runCatching { GlobalContext.get().get<RtspSettings>() }.getOrNull() }
    val settingsFallback = remember { MutableStateFlow(RtspSettings.Data()) }
    val settings by (rtspSettings?.data ?: settingsFallback).collectAsState()
    val scope = rememberCoroutineScope()
    var serverAddressDraft by rememberSaveable { mutableStateOf("") }
    var serverPathDraft by rememberSaveable { mutableStateOf("") }
    var serverPortDraft by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(settings.serverAddress, settings.serverPath, settings.serverPort) {
        serverAddressDraft = settings.serverAddress
        serverPathDraft = settings.serverPath
        serverPortDraft = settings.serverPort.toString()
    }
    val updateSettings: (RtspSettings.Data.() -> RtspSettings.Data) -> Unit = { transform ->
        rtspSettings?.let { store -> scope.launch { store.updateData(transform) } }
    }
    val showSession = section == null || section == "公开媒体会话"
    val showNetwork = section == null || section == "网络"
    val showVideo = section == null || section == "视频"
    val showAudio = section == null || section == "音频"
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 26.dp)) {
        V5BackButton("连接", onBack)
        V5PageHeading(section ?: "媒体会话", "") {}
        if (showSession) V5Panel(modifier = Modifier.padding(top = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("会话状态", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
                V5Pill(if (transport.status == RtspTransportStatus.STREAMING || transport.status == RtspTransportStatus.STREAMING_NO_CONSUMER) "传输中" else "未开始", transport.status == RtspTransportStatus.STREAMING || transport.status == RtspTransportStatus.STREAMING_NO_CONSUMER)
            }
        }
        if (rtspSettings == null) {
            V5Panel(modifier = Modifier.padding(top = 10.dp)) { Text("RTSP 设置仓储不可用", color = NativeV5Tokens.Warning, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font); Text("未显示可编辑的假开关。请先检查当前流媒体内核是否完成 Koin 初始化。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp)) }
            return@Column
        }
        if (showSession) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("采集与会话", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            V5ToggleRow("保持唤醒", "屏幕流运行期间保持设备唤醒。", settings.keepAwake) { updateSettings { copy(keepAwake = it) } }
            V5ToggleRow("休眠时停止", "屏幕关闭时结束当前会话。", settings.stopOnSleep) { updateSettings { copy(stopOnSleep = it) } }
            V5ToggleRow("配置变化时停止", "旋转或配置变化时不继续复用采集。", settings.stopOnConfigurationChange) { updateSettings { copy(stopOnConfigurationChange = it) } }
        }
        if (showNetwork) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("传输与服务端", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            V5Segmented(listOf("服务端", "客户端"), if (settings.mode == RtspSettings.Values.Mode.SERVER) 0 else 1) { updateSettings { copy(mode = if (it == 0) RtspSettings.Values.Mode.SERVER else RtspSettings.Values.Mode.CLIENT) } }
            if (settings.mode == RtspSettings.Values.Mode.SERVER) {
                V5SettingsTextInput("服务端端口", serverPortDraft, "8554", Modifier.padding(top = 10.dp), onValueChange = { serverPortDraft = it }, onApply = { serverPortDraft.toIntOrNull()?.takeIf { it in 1..65535 }?.let { port -> updateSettings { copy(serverPort = port) } } })
                V5SettingsTextInput("RTSP 路径", serverPathDraft, "screen", onValueChange = { serverPathDraft = it }, onApply = { if (serverPathDraft.isNotBlank()) updateSettings { copy(serverPath = serverPathDraft.trim()) } })
                V5Segmented(listOf("协议自动", "TCP", "UDP"), settings.serverProtocol.ordinal) { updateSettings { copy(serverProtocol = RtspSettings.Values.ProtocolPolicy.entries[it]) } }
                V5ToggleRow("IPv4", "允许在 IPv4 地址上监听。", settings.enableIPv4) { updateSettings { copy(enableIPv4 = it) } }
                V5ToggleRow("IPv6", "允许在 IPv6 地址上监听。", settings.enableIPv6) { updateSettings { copy(enableIPv6 = it) } }
            } else {
                V5SettingsTextInput("目标 RTSP 地址", serverAddressDraft, "rtsp://…", Modifier.padding(top = 10.dp), onValueChange = { serverAddressDraft = it }, onApply = { if (serverAddressDraft.isNotBlank()) updateSettings { copy(serverAddress = serverAddressDraft.trim()) } })
                V5Segmented(listOf("协议自动", "TCP", "UDP"), settings.clientProtocol.ordinal) { updateSettings { copy(clientProtocol = RtspSettings.Values.ProtocolPolicy.entries[it]) } }
            }
        }
        if (showVideo) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("视频", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            V5ToggleRow("自动选择视频编码", "由内核按设备能力选择编码器。", settings.videoCodecAutoSelect) { updateSettings { copy(videoCodecAutoSelect = it) } }
            V5Segmented(listOf("25%", "50%", "75%", "100%"), listOf(25F, 50F, 75F, 100F).indexOf(settings.videoResizeFactor).coerceAtLeast(1)) { updateSettings { copy(videoResizeFactor = listOf(25F, 50F, 75F, 100F)[it]) } }
            V5Segmented(listOf("15 fps", "24 fps", "30 fps", "60 fps"), listOf(15, 24, 30, 60).indexOf(settings.videoFps).coerceAtLeast(2)) { updateSettings { copy(videoFps = listOf(15, 24, 30, 60)[it]) } }
            V5Segmented(listOf("1.5 Mbps", "3 Mbps", "4.5 Mbps", "6 Mbps"), listOf(1_500_000, 3_000_000, 4_500_000, 6_000_000).indexOf(settings.videoBitrateBits).coerceAtLeast(2)) { updateSettings { copy(videoBitrateBits = listOf(1_500_000, 3_000_000, 4_500_000, 6_000_000)[it]) } }
        }
        if (showAudio) V5Panel(modifier = Modifier.padding(top = 10.dp)) {
            Text("音频", color = NativeV5Tokens.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
            Text("设备播放音频是 ASR 同源音轨的配置前提，仍需 Android 授权和 MediaProjection 支持。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
            V5ToggleRow("设备播放音频", "将设备音频纳入新启动的授权会话。", settings.enableDeviceAudio) { updateSettings { copy(enableDeviceAudio = it) } }
            V5ToggleRow("麦克风", "将麦克风音轨纳入新启动的授权会话。", settings.enableMic) { updateSettings { copy(enableMic = it) } }
            V5ToggleRow("双声道", "在设备支持时使用立体声输出。", settings.stereoAudio) { updateSettings { copy(stereoAudio = it) } }
            V5ToggleRow("回声消除", "启用内核音频回声消除。", settings.audioEchoCanceller) { updateSettings { copy(audioEchoCanceller = it) } }
            V5ToggleRow("降噪", "启用内核音频降噪。", settings.audioNoiseSuppressor) { updateSettings { copy(audioNoiseSuppressor = it) } }
            V5Segmented(listOf("64 kbps", "128 kbps", "192 kbps"), listOf(64_000, 128_000, 192_000).indexOf(settings.audioBitrateBits).coerceAtLeast(1)) { updateSettings { copy(audioBitrateBits = listOf(64_000, 128_000, 192_000)[it]) } }
        }
    }
}

/**
 * Native secondary routes corresponding to the clickable V5 prototype.  They
 * deliberately keep a real back stack instead of routing every action back
 * to Discover, which was the original interaction gap.
 */
@Composable
private fun V5SecondaryInteractionPage(
    route: V5Route,
    title: String,
    subject: String,
    activeCandidate: CandidateCard?,
    analysisFilterIndex: Int,
    onApplyAnalysisFilter: (Int) -> Unit,
    onBack: () -> Unit,
    onOpen: (V5Route, String, String) -> Unit,
) {
    val context = LocalContext.current
    val graphRepository = remember { MobileAppServices.knowledgeVault(context) }
    val graphEventStore = remember { AndroidKnowledgeGraphEventStore(context.applicationContext) }
    val candidateStore = remember { MobileAppServices.candidateStore(context) }
    val allCandidates by candidateStore.observe().collectAsState(initial = emptyList())
    val learningResponseStore = remember { MobileAppServices.learningResponseStore(context) }
    val graphSnapshot by graphRepository.observeGraph().collectAsState(initial = cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot.empty())
    val mobileSessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val currentMobileSession by mobileSessionStore.current.collectAsState()
    val scope = rememberCoroutineScope()
    var draft by rememberSaveable(route, subject) { mutableStateOf("") }
    var selected by rememberSaveable(route, subject) { mutableStateOf(if (route == V5Route.FILTER) analysisFilterIndex else 0) }
    var knowledgeTab by rememberSaveable(route, subject) { mutableStateOf(0) }
    var operationStatus by rememberSaveable(route, subject) { mutableStateOf<String?>(null) }
    val transportFacade = rememberStartedRtspFacade()
    val transportFallback = remember { MutableStateFlow(RtspTransportSnapshot(RtspTransportStatus.IDLE, 0, null, false, null)) }
    val transport by (transportFacade?.state ?: transportFallback).collectAsState()
    val pageTitle = title.ifBlank {
        when (route) {
            V5Route.EVIDENCE -> "捕获窗口与证据"
            V5Route.SOURCES -> "材料与来源"
            V5Route.SOURCE_DETAIL -> "来源详情"
            V5Route.NODE_DETAIL, V5Route.KNOWLEDGE_NOTE -> "知识节点"
            V5Route.FILTER -> "筛选"
            V5Route.PROFILE_EVIDENCE -> "知识证据索引"
            V5Route.EVIDENCE_ITEM -> "证据条目"
            V5Route.SESSION_DETAIL -> "会话与传输"
            V5Route.PC_DETAIL -> "PC 中枢回传"
            V5Route.DEVICE_DETAIL -> "设备链路"
            V5Route.NOTICE_HISTORY -> "通知历史"
            V5Route.EXPORT -> "本地数据导出"
            V5Route.AUDIT -> "删除审计"
            V5Route.CONCEPT_DETAIL -> "概念说明"
            V5Route.KNOWLEDGE_CREATE -> "新建知识节点"
            V5Route.KNOWLEDGE_SEARCH -> "检索知识节点"
            V5Route.KNOWLEDGE_TOOLS -> "图谱管理"
            V5Route.KNOWLEDGE_LINK -> "创建双向链接"
            V5Route.KNOWLEDGE_RENAME -> "重命名节点"
            V5Route.KNOWLEDGE_DELETE -> "删除节点"
            V5Route.KNOWLEDGE_SOURCE -> "节点来源"
            V5Route.SENSOR_STATUS -> "状态流与质量"
            else -> "详情"
        }
    }
    val deviceDetail = route == V5Route.DEVICE_DETAIL
    val deviceIsGlasses = subject.contains("眼镜") || subject.contains("EEG", ignoreCase = true)
    val visiblePageTitle = if (deviceDetail) if (deviceIsGlasses) "智能眼镜 / EEG" else "手表" else pageTitle
    val visiblePageSubtitle = if (deviceDetail) "设备链路" else ""
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 58.dp, bottom = 28.dp)) {
        V5BackButton("返回", onBack)
        V5PageHeading(visiblePageTitle, visiblePageSubtitle) {}
        when (route) {
            V5Route.EVIDENCE -> {
                V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                    Text("同源捕获窗口", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                    if (activeCandidate == null) {
                        Text("尚未选择真实候选卡，无法展示捕获窗口或证据引用。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                    } else {
                        Text("来源：${activeCandidate.source.name} · PTS ${activeCandidate.startPtsNs}–${activeCandidate.endPtsNs} · visit ${activeCandidate.visitId}", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                        Text("证据引用：${activeCandidate.evidenceRefs.joinToString("、") { it.value }}", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
                        V5SecondaryButton("打开本条候选的证据事实", Modifier.fillMaxWidth().padding(top = 9.dp)) { onOpen(V5Route.EVIDENCE_ITEM, "证据条目", activeCandidate.id.value) }
                    }
                }
                if (activeCandidate != null) V5SecondaryButton("查看受控学习材料", Modifier.fillMaxWidth().padding(top = 10.dp)) { onOpen(V5Route.SOURCES, "材料与来源", activeCandidate.visitId) }
            }
            V5Route.SOURCES -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("受控学习材料", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("当前候选尚未携带可展示的同源材料索引；不会用网页示例法规或案例填充此页。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
            }
            V5Route.SOURCE_DETAIL, V5Route.EVIDENCE_ITEM, V5Route.KNOWLEDGE_SOURCE -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text(if (route == V5Route.EVIDENCE_ITEM) "候选证据事实" else subject.ifBlank { "可回溯记录" }, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                val facts = activeCandidate?.facts.orEmpty()
                if (route == V5Route.EVIDENCE_ITEM && facts.isNotEmpty()) facts.forEach { fact -> Text("${fact.lane.name} · ${fact.text}", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp)) }
                else Text("当前没有可展示的同源详情；不会将未核验材料伪装成结论。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
            }
            V5Route.CONCEPT_DETAIL -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text(subject.ifBlank { "当前内容概念" }, color = NativeV5Tokens.Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("当前尚未收到该内容的受控概念说明包；不会用原型示例正文填充。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 19.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 7.dp))
            }
            V5Route.NODE_DETAIL, V5Route.KNOWLEDGE_NOTE -> {
                val node = graphSnapshot.nodes.firstOrNull { it.label == subject }
                V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                    Text(node?.label ?: subject.ifBlank { "生成式 AI" }, color = NativeV5Tokens.Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                    V5Segmented(listOf("笔记", "双向链接", "来源证据"), knowledgeTab, compact = true) { knowledgeTab = it }
                    if (knowledgeTab == 0) {
                        LaunchedEffect(node?.id) { if (draft.isBlank()) draft = node?.note.orEmpty() }
                        OutlinedTextField(value = draft, onValueChange = { draft = it; operationStatus = null }, label = { Text("节点笔记") }, placeholder = { Text("记录概念、来源或待确认链接") }, modifier = Modifier.fillMaxWidth().padding(top = 9.dp), minLines = 4)
                        V5PrimaryButton("保存手工编辑", Modifier.fillMaxWidth().padding(top = 9.dp), enabled = node != null && draft.isNotBlank()) {
                            val target = node ?: return@V5PrimaryButton
                            scope.launch {
                                val saved = if (target.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) graphRepository.confirmSuggestion(target.id) else graphRepository.updateStudentNode(target.id, target.label, draft.trim())
                                operationStatus = if (saved != null) "节点笔记已写入本机知识库" else "该节点不可由学生直接修改"
                            }
                        }
                    } else if (knowledgeTab == 1) {
                        Text("已建立 ${node?.let { current -> graphSnapshot.edges.count { it.from == current.id || it.to == current.id } } ?: 0} 条关联。", color = NativeV5Tokens.Muted, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                        if (node?.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) V5SecondaryButton("采纳 AI 建议关系", Modifier.fillMaxWidth()) { scope.launch { operationStatus = if (graphRepository.confirmSuggestion(node.id) != null) "AI 建议已确认并写入图谱" else "未能确认该建议" } }
                        V5SecondaryButton("创建双向链接", Modifier.fillMaxWidth()) { onOpen(V5Route.KNOWLEDGE_LINK, "创建双向链接", subject) }
                    } else {
                        Text("来源证据保持在本地受控范围，可从证据页查看范围和引用标识。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                        V5SecondaryButton("查看节点来源", Modifier.fillMaxWidth()) { onOpen(V5Route.KNOWLEDGE_SOURCE, "节点来源", subject) }
                    }
                    V5SecondaryButton("重命名节点", Modifier.fillMaxWidth()) { onOpen(V5Route.KNOWLEDGE_RENAME, "重命名节点", subject) }
                    V5SecondaryButton("删除节点", Modifier.fillMaxWidth(), enabled = node?.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED) { onOpen(V5Route.KNOWLEDGE_DELETE, "删除节点", subject) }
                    operationStatus?.let { Text(it, color = if (it.startsWith("节点") || it.startsWith("AI")) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
                }
            }
            V5Route.KNOWLEDGE_CREATE, V5Route.KNOWLEDGE_RENAME -> {
                val existing = graphSnapshot.nodes.firstOrNull { it.label == subject }
                V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                    OutlinedTextField(value = draft, onValueChange = { draft = it; operationStatus = null }, label = { Text(if (route == V5Route.KNOWLEDGE_CREATE) "节点名称" else "新的节点名称") }, modifier = Modifier.fillMaxWidth())
                    V5PrimaryButton(if (route == V5Route.KNOWLEDGE_CREATE) "创建节点并打开笔记" else "保存名称", Modifier.fillMaxWidth().padding(top = 9.dp), enabled = draft.isNotBlank() && (route == V5Route.KNOWLEDGE_CREATE || existing?.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED)) {
                        scope.launch {
                            if (route == V5Route.KNOWLEDGE_CREATE) {
                                val session = currentMobileSession ?: mobileSessionStore.open()
                                val created = graphRepository.createStudentNode(StudentKnowledgeNodeDraft(KnowledgeGraphNodeId("student:" + UUID.randomUUID()), draft.trim(), session.id, existing?.evidenceRefs.orEmpty(), ""))
                                existing?.let { parent -> graphRepository.createStudentEdge(StudentKnowledgeEdgeDraft(KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()), parent.id, created.id, KnowledgeRelationship.PART_OF)) }
                                onOpen(V5Route.NODE_DETAIL, "知识节点笔记", created.label)
                            } else if (existing != null) {
                                operationStatus = if (graphRepository.updateStudentNode(existing.id, draft.trim(), existing.note) != null) "节点名称已更新" else "该节点不可由学生重命名"
                            }
                        }
                    }
                    operationStatus?.let { Text(it, color = NativeV5Tokens.Positive, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
                }
            }
            V5Route.KNOWLEDGE_LINK -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("关联到另一个知识节点", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                val source = graphSnapshot.nodes.firstOrNull { it.label == subject }
                val targets = graphSnapshot.nodes.filter { it.id != source?.id }.take(4)
                if (targets.isEmpty()) Text("请先在知识全览中至少创建两个节点。", color = NativeV5Tokens.Muted, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) else {
                    V5Segmented(targets.map { it.label }, selected.coerceIn(0, targets.lastIndex)) { selected = it }
                    V5PrimaryButton("创建双向链接", Modifier.fillMaxWidth().padding(top = 9.dp), enabled = source != null) {
                        val from = source ?: return@V5PrimaryButton
                        val to = targets[selected.coerceIn(0, targets.lastIndex)]
                        scope.launch {
                            val alreadyLinked = graphSnapshot.edges.any { (it.from == from.id && it.to == to.id) || (it.from == to.id && it.to == from.id) }
                            operationStatus = if (alreadyLinked) "该双向关系已存在" else {
                                graphRepository.createStudentEdge(StudentKnowledgeEdgeDraft(KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()), from.id, to.id, KnowledgeRelationship.RELATED_TO))
                                graphRepository.createStudentEdge(StudentKnowledgeEdgeDraft(KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()), to.id, from.id, KnowledgeRelationship.RELATED_TO))
                                "双向链接已写入本机图谱"
                            }
                        }
                    }
                }
                operationStatus?.let { Text(it, color = NativeV5Tokens.Positive, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
            }
            V5Route.KNOWLEDGE_DELETE -> V5Panel(modifier = Modifier.padding(top = 12.dp), tint = Color(0xFFFFF8F6), border = Color(0xFFF2D9D2)) {
                Text("删除“${subject.ifBlank { "当前节点" }}”", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("删除后会进入本地回收站，不会静默清除关联证据。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
                val node = graphSnapshot.nodes.firstOrNull { it.label == subject }
                V5PrimaryButton("移入回收站", Modifier.fillMaxWidth().padding(top = 9.dp), enabled = node?.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED) { val target = node ?: return@V5PrimaryButton; scope.launch { operationStatus = if (graphRepository.removeNode(target.id)) "节点已移入本机回收站" else "未能删除该节点" } }
                operationStatus?.let { Text(it, color = NativeV5Tokens.Positive, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
            }
            V5Route.KNOWLEDGE_SEARCH, V5Route.KNOWLEDGE_TOOLS -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                if (route == V5Route.KNOWLEDGE_SEARCH) {
                    OutlinedTextField(value = draft, onValueChange = { draft = it }, label = { Text("节点、标签或未链接提及") }, modifier = Modifier.fillMaxWidth())
                    V5PrimaryButton("搜索知识库", Modifier.fillMaxWidth().padding(top = 9.dp), enabled = draft.isNotBlank()) { operationStatus = "搜索结果：" + graphSnapshot.nodes.filter { it.label.contains(draft.trim(), ignoreCase = true) || it.note.contains(draft.trim(), ignoreCase = true) }.joinToString("、") { it.label }.ifBlank { "未找到匹配节点" } }
                    operationStatus?.let { Text(it, color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
                } else {
                    // 管理页必须读取真实图谱快照和本机持久化事件，不能继续用
                    // “已定位”toast 假装管理动作已经发生。
                    val toolLabels = listOf("关系", "未链接", "待审核", "历史", "删除")
                    var toolIndex by rememberSaveable(route) { mutableStateOf(0) }
                    V5Segmented(toolLabels, toolIndex, compact = true) { toolIndex = it }
                    V5SecondaryButton("检索节点", Modifier.fillMaxWidth().padding(top = 4.dp)) { onOpen(V5Route.KNOWLEDGE_SEARCH, "检索知识节点", "") }
                    val connectedIds = graphSnapshot.edges.flatMap { listOf(it.from, it.to) }.toSet()
                    val nodeById = graphSnapshot.nodes.associateBy { it.id }
                    val events = graphEventStore.recent()
                    when (toolIndex) {
                        0 -> {
                            Text("关系类型与当前双向链接", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                            if (graphSnapshot.edges.isEmpty()) Text("当前没有已写入的关系。可从节点详情创建双向链接。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
                            else graphSnapshot.edges.forEach { edge ->
                                val from = nodeById[edge.from]?.label ?: edge.from.value
                                val to = nodeById[edge.to]?.label ?: edge.to.value
                                V5SecondaryButton("$from · ${edge.relationship.name} · $to", Modifier.fillMaxWidth()) { onOpen(V5Route.NODE_DETAIL, "知识节点笔记", from) }
                            }
                        }
                        1 -> {
                            Text("未链接节点", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                            val unlinked = graphSnapshot.nodes.filter { it.id !in connectedIds }
                            if (unlinked.isEmpty()) Text("当前节点都至少有一条关系。", color = NativeV5Tokens.Muted, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
                            else unlinked.forEach { node -> V5SecondaryButton("打开 ${node.label}", Modifier.fillMaxWidth()) { onOpen(V5Route.NODE_DETAIL, "知识节点笔记", node.label) } }
                        }
                        2 -> {
                            Text("AI 建议收件箱", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                            val pending = graphSnapshot.nodes.filter { it.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT }
                            if (pending.isEmpty()) Text("没有待学生确认的知识节点建议。", color = NativeV5Tokens.Muted, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
                            else pending.forEach { node -> V5SecondaryButton("审核 ${node.label}", Modifier.fillMaxWidth()) { onOpen(V5Route.NODE_DETAIL, "知识节点笔记", node.label) } }
                        }
                        3 -> {
                            Text("本机图谱变更记录", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                            val history = events.filterNot { it.operation == "DELETE" }
                            if (history.isEmpty()) Text("尚无本机图谱变更记录。", color = NativeV5Tokens.Muted, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
                            else history.take(12).forEach { event -> Text("${event.operation} · ${event.entityKind} · ${event.state} · ${event.occurredAt.take(16)}", color = NativeV5Tokens.Ink, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 7.dp)) }
                        }
                        else -> {
                            Text("删除记录", color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 10.dp))
                            val deleted = events.filter { it.operation == "DELETE" }
                            if (deleted.isEmpty()) Text("尚无本机删除记录；当前版本不会伪造可恢复条目。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp))
                            else deleted.take(12).forEach { event -> Text("已删除 ${event.entityKind} · ${event.entityId.take(18)} · ${event.occurredAt.take(16)}", color = NativeV5Tokens.Ink, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 7.dp)) }
                        }
                    }
                }
            }
            V5Route.FILTER -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("统计范围", color = NativeV5Tokens.Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                V5_ANALYSIS_FILTERS.forEachIndexed { index, label ->
                    V5SecondaryButton(if (selected == index) "✓ $label" else label, Modifier.fillMaxWidth()) { selected = index; operationStatus = "待应用：$label" }
                }
                V5PrimaryButton("应用筛选并返回", Modifier.fillMaxWidth().padding(top = 9.dp)) { onApplyAnalysisFilter(selected); onBack() }
                V5SecondaryButton("证据索引", Modifier.fillMaxWidth()) { onOpen(V5Route.PROFILE_EVIDENCE, "知识证据索引", "") }
                operationStatus?.let { Text(it, color = NativeV5Tokens.Positive, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 8.dp)) }
            }
            V5Route.PROFILE_EVIDENCE -> {
                if (allCandidates.isEmpty()) {
                    V5Panel(modifier = Modifier.padding(top = 12.dp)) { Text("暂无可回溯证据", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) }
                } else {
                    allCandidates.sortedByDescending { it.endPtsNs }.take(30).forEach { candidate ->
                        V5Panel(modifier = Modifier.padding(top = 7.dp).clickable { onOpen(V5Route.EVIDENCE_ITEM, "证据条目", candidate.id.value) }) {
                            Text(candidate.displayExcerpt.ifBlank { candidate.id.value }, color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${candidate.source.name} · PTS ${candidate.startPtsNs}–${candidate.endPtsNs}", color = NativeV5Tokens.Muted, fontSize = 10.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 2.dp))
                        }
                    }
                }
            }
            V5Route.SESSION_DETAIL -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                if (subject == "眼镜第一视角") {
                    Text("第一视角会话", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                    Text("眼镜片段先在本机封存，再以手机时间轴建立可追溯锚点；状态流只作质量辅助，不生成注意力或人格结论。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        V5MiniFact("封存片段", "本机优先", Modifier.weight(1f))
                        V5MiniFact("时间锚", "待手机对齐", Modifier.weight(1f))
                    }
                    V5SecondaryButton("查看眼镜 / EEG 设备链路", Modifier.fillMaxWidth().padding(top = 9.dp)) { onOpen(V5Route.DEVICE_DETAIL, "智能眼镜 / EEG", "眼镜") }
                    V5SecondaryButton("查看状态流与质量", Modifier.fillMaxWidth()) { onOpen(V5Route.SENSOR_STATUS, "状态流与质量", "智能眼镜 / EEG") }
                } else {
                    Text("会话状态：${transport.status.name}", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                    Text("消费端：${transport.activeConsumerCount} · 端点：${transport.endpoint ?: "未建立"}", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 5.dp))
                    V5SecondaryButton("媒体会话", Modifier.fillMaxWidth().padding(top = 5.dp)) { onOpen(V5Route.MEDIA, "媒体会话", "") }
                    V5SecondaryButton("查看 PC 回传", Modifier.fillMaxWidth()) { onOpen(V5Route.PC_DETAIL, "PC 中枢回传", "候选、学习回应和图谱事件") }
                    V5SecondaryButton("查看设备链路", Modifier.fillMaxWidth()) { onOpen(V5Route.DEVICE_DETAIL, "设备链路", "眼镜、手表与手机") }
                }
            }
            V5Route.PC_DETAIL -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text(subject.ifBlank { "本地 PC 中枢" }, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("负责手机媒体分析、证据存储、结果回传；同时独立采集 PC 学习路径，不是手机学习的固定下游。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                Row(modifier = Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    V5MiniFact("证据库", "本地可追溯", Modifier.weight(1f))
                    V5MiniFact("数据回传", "候选卡与回执", Modifier.weight(1f))
                }
            }
            V5Route.DEVICE_DETAIL -> {
                val glasses = deviceIsGlasses
                val deviceTitle = if (glasses) "智能眼镜 / EEG" else "手表"
                val control = if (glasses) "BLE 低功耗控制链：眼镜 → 手机" else "BLE 低功耗数据链：手表 → 手机"
                val data = if (glasses) "高带宽视觉 / EEG 数据链：眼镜 → 手机（Wi‑Fi Direct / 受控局域网）" else "手机汇聚后经局域网安全转发：手机 → PC"
                val fallback = if (glasses) "眼镜与手机按时间轴分片封存；回家或受信网络可用后由手机同步 PC" else "PC 不可达时手机本地队列暂存，恢复后批量回传"
                Text("控制、数据与回退三条链路分开显示；未配对不代表可用。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 12.dp))
                V5Panel(modifier = Modifier.padding(top = 10.dp), contentPadding = 0.dp) {
                    listOf(
                        Triple("控制链", control, "待配对"),
                        Triple("数据链", data, "未接入"),
                        Triple("离线回退", fallback, "已定义"),
                    ).forEachIndexed { index, (label, detail, status) ->
                        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(label, color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                                Text(detail, color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 16.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 3.dp))
                            }
                            V5Pill(status, positive = index == 2)
                        }
                    }
                }
                V5Panel(modifier = Modifier.padding(top = 10.dp)) {
                    Text("同步与质量", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                    Text("第一视角记录先以手机本地时间轴为锚；回家后再与 PC 记录校准。显示时钟偏差、丢包和最近心跳；质量不足时只记录，不参与知识融合或提醒。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                    V5SecondaryButton("查看状态流与质量", Modifier.fillMaxWidth().padding(top = 9.dp)) { onOpen(V5Route.SENSOR_STATUS, "状态流与质量", deviceTitle) }
                }
            }
            V5Route.SENSOR_STATUS -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("状态流与质量", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("仅显示设备可用性、采样质量与时间对齐；不输出注意力、人格、能力或医学结论。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 4.dp))
                Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    V5MiniFact("EEG", "未接入", Modifier.weight(1f))
                    V5MiniFact("EDA", "未接入", Modifier.weight(1f))
                    V5MiniFact("时间轴", if (transport.timing != null) "屏幕流已锚定" else "待锚定", Modifier.weight(1f))
                }
            }
            V5Route.NOTICE_HISTORY -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("L1 系统通知", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("L1 仅在 PC 回传完整证据且满足资格时通过 Android 系统通知通道触发；这里不镜像、不伪造通知内容。L2–L4 不使用系统推送。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                V5SecondaryButton("打开系统通知设置", Modifier.fillMaxWidth().padding(top = 10.dp)) {
                    context.startActivity(
                        Intent(Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS)
                            .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                            .putExtra(Settings.EXTRA_CHANNEL_ID, AndroidStudentNotice.CHANNEL_ID)
                    )
                }
            }
            V5Route.EXPORT -> V5Panel(modifier = Modifier.padding(top = 12.dp)) {
                Text("本地导出", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("导出候选证据索引、学生主动回执、知识节点/关系与本机审计；不导出原始媒体、设备标识、配对凭据或模型密钥。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                V5PrimaryButton("导出 JSON 到下载目录", Modifier.fillMaxWidth().padding(top = 10.dp)) {
                    scope.launch {
                        operationStatus = "正在生成本地导出…"
                        operationStatus = runCatching {
                            LocalLearningDataExporter.exportJson(
                                context = context,
                                candidates = candidateStore.snapshot(),
                                graph = graphSnapshot,
                                responses = learningResponseStore.snapshot(),
                                graphEvents = graphEventStore.recent(200),
                            )
                        }.fold(
                            onSuccess = { fileName -> "已保存到下载目录：$fileName" },
                            onFailure = { error -> "本地导出失败：${error.message?.take(120) ?: "未知错误"}" },
                        )
                    }
                }
                operationStatus?.let { Text(it, color = if (it.startsWith("已保存")) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 9.dp)) }
            }
            V5Route.AUDIT -> V5Panel(modifier = Modifier.padding(top = 12.dp)) { Text("数据治理记录", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font); Text("保留策略已更新：原始证据 30 天，版本记录保留。撤回后关联卡片与画像条目失效。", color = NativeV5Tokens.Muted, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp)) }
            else -> Unit
        }
    }
}

@Composable
private fun V5Toast(message: String, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.padding(horizontal = 28.dp, vertical = 88.dp).clickable(onClick = onDismiss), shape = RoundedCornerShape(12.dp), color = Color(0xEE20252B), shadowElevation = 12.dp) {
        Text(message, color = Color.White, fontSize = 11.sp, lineHeight = 16.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp))
    }
}

@Composable
private fun V5PageHeading(title: String, subtitle: String, right: String? = null, onRight: (() -> Unit)? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = NativeV5Tokens.Ink, fontSize = 22.sp, lineHeight = 26.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f))
        if (right != null) TextButton(onClick = onRight ?: {}, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 0.dp)) { Text(right, color = NativeV5Tokens.Accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) }
    }
}

@Composable
private fun V5BackButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    TextButton(onClick = onClick, modifier = modifier, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            V5LineIcon(V5Icon.BACK, tint = NativeV5Tokens.Accent, contentDescription = "返回$label", modifier = Modifier.size(16.dp))
            Text(label, color = NativeV5Tokens.Accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
        }
    }
}

@Composable
private fun V5Panel(modifier: Modifier = Modifier, tint: Color = Color.White, border: Color = Color(0xFFE8EDF2), accent: Color? = null, contentPadding: androidx.compose.ui.unit.Dp = 10.dp, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier = modifier, shape = RoundedCornerShape(12.dp), color = tint, border = androidx.compose.foundation.BorderStroke(1.dp, border), shadowElevation = 1.dp) {
        Row {
            if (accent != null) Spacer(Modifier.width(3.dp).padding(vertical = 14.dp).background(accent, RoundedCornerShape(topEnd = 3.dp, bottomEnd = 3.dp)))
            Column(Modifier.padding(contentPadding), content = content)
        }
    }
}

/** Compact navigation rows are not call-to-action buttons: they keep source
 * and material entry points dense, readable, and visually distinct from the
 * page's primary learning action. */
private data class V5ActionListItem(val title: String, val detail: String = "", val onClick: () -> Unit)

@Composable
private fun V5ActionList(modifier: Modifier = Modifier, rows: List<V5ActionListItem>) {
    V5Panel(modifier = modifier, contentPadding = 0.dp) {
        rows.forEachIndexed { index, row ->
            Row(
                modifier = Modifier.fillMaxWidth().clickable(onClick = row.onClick).padding(horizontal = 11.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(row.title, color = NativeV5Tokens.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (row.detail.isNotBlank()) Text(row.detail, color = NativeV5Tokens.Muted, fontSize = 10.sp, lineHeight = 13.sp, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 1.dp))
                }
                V5LineIcon(V5Icon.FORWARD, tint = NativeV5Tokens.IconMuted, contentDescription = "打开${row.title}", modifier = Modifier.size(17.dp))
            }
            if (index < rows.lastIndex) Spacer(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFFE8EDF2)))
        }
    }
}

@Composable
private fun V5Pill(label: String, positive: Boolean) { Surface(shape = RoundedCornerShape(999.dp), color = if (positive) NativeV5Tokens.PositiveSoft else NativeV5Tokens.WarningSoft) { Text(label, color = if (positive) NativeV5Tokens.Positive else NativeV5Tokens.Warning, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp)) } }

@Composable
private fun V5ToggleRow(label: String, detail: String, checked: Boolean, enabled: Boolean = true, onCheckedChange: (Boolean) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().padding(top = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        TextButton(onClick = { onCheckedChange(!checked) }, enabled = enabled, modifier = Modifier.padding(start = 10.dp)) {
            Text(if (checked) "已开启" else "已关闭", color = if (checked) NativeV5Tokens.Positive else NativeV5Tokens.Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
        }
    }
}

/** Settings forms use one compact row per value.  Applying every field on a
 * separate line made the service configuration taller than the chat surface. */
@Composable
private fun V5CompactConfigInput(label: String, value: String, placeholder: String, onValueChange: (String) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = NativeV5Tokens.Muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.width(42.dp))
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = TextStyle(color = NativeV5Tokens.Ink, fontSize = 12.sp, fontFamily = NativeV5Tokens.Font),
            modifier = Modifier.weight(1f).height(38.dp).clip(RoundedCornerShape(8.dp)).border(1.dp, Color(0xFFD9E0E7), RoundedCornerShape(8.dp)).padding(horizontal = 9.dp, vertical = 7.dp),
            decorationBox = { inner ->
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.CenterStart) {
                    if (value.isBlank()) Text(placeholder, color = NativeV5Tokens.Muted, fontSize = 11.sp, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    inner()
                }
            },
        )
    }
}

@Composable
private fun V5SettingsTextInput(
    label: String,
    value: String,
    placeholder: String,
    modifier: Modifier = Modifier,
    onValueChange: (String) -> Unit,
    onApply: () -> Unit,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Text(label, color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
        Row(modifier = Modifier.fillMaxWidth().padding(top = 5.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value = value, onValueChange = onValueChange, placeholder = { Text(placeholder, fontSize = 13.sp, fontFamily = NativeV5Tokens.Font) }, singleLine = true, modifier = Modifier.weight(1f))
            TextButton(onClick = onApply, modifier = Modifier.padding(start = 6.dp)) { Text("应用", color = NativeV5Tokens.Accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font) }
        }
    }
}

@Composable
private fun V5SecondaryButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) { TextButton(onClick = onClick, enabled = enabled, modifier = modifier.height(36.dp), shape = RoundedCornerShape(10.dp)) { Text(label, color = if (enabled) NativeV5Tokens.Accent else NativeV5Tokens.Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis) } }

@Composable
private fun V5IconAction(icon: V5Icon, contentDescription: String, onClick: () -> Unit, active: Boolean = false, enabled: Boolean = true, primary: Boolean = false) {
    Surface(
        modifier = Modifier.padding(horizontal = 3.dp).size(36.dp).clip(RoundedCornerShape(10.dp)).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(10.dp),
        color = when { primary && enabled -> NativeV5Tokens.Accent; active -> Color(0xFFEAF4FF); else -> Color(0xFFF3F6F9) },
    ) {
        Box(contentAlignment = Alignment.Center) {
            V5LineIcon(icon, tint = when { primary && enabled -> Color.White; active -> NativeV5Tokens.Accent; else -> NativeV5Tokens.IconMuted }, contentDescription = contentDescription, modifier = Modifier.size(17.dp))
        }
    }
}

@Composable
private fun V5PrimaryButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) { Surface(modifier = modifier.height(36.dp).clip(RoundedCornerShape(10.dp)).clickable(enabled = enabled, onClick = onClick), shape = RoundedCornerShape(10.dp), color = if (enabled) NativeV5Tokens.Accent else NativeV5Tokens.Quiet) { Box(contentAlignment = Alignment.Center) { Text(label, color = if (enabled) Color.White else NativeV5Tokens.Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis) } } }

@Composable
private fun V5Segmented(items: List<String>, selected: Int, compact: Boolean = false, onSelect: (Int) -> Unit) { Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp).clip(RoundedCornerShape(10.dp)).background(Color(0xFFEFF2F5)).padding(3.dp), horizontalArrangement = Arrangement.spacedBy(2.dp)) { items.forEachIndexed { index, item -> val active = index == selected; TextButton(onClick = { onSelect(index) }, modifier = Modifier.weight(1f).height(if (compact) 36.dp else 32.dp), shape = RoundedCornerShape(8.dp), contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) { Text(item, color = if (active) NativeV5Tokens.Accent else NativeV5Tokens.Muted, fontSize = 10.sp, lineHeight = 14.sp, maxLines = 1, fontWeight = if (active) FontWeight.Bold else FontWeight.Medium, fontFamily = NativeV5Tokens.Font) } } }
}

@Composable
private fun V5MiniFact(label: String, value: String, modifier: Modifier) { Surface(modifier = modifier, shape = RoundedCornerShape(10.dp), color = Color(0xFFF5F7F9)) { Column(Modifier.padding(9.dp)) { Text(label, color = NativeV5Tokens.Muted, fontSize = 9.sp, fontFamily = NativeV5Tokens.Font); Text(value, color = NativeV5Tokens.Ink, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 3.dp), maxLines = 1, overflow = TextOverflow.Ellipsis) } } }

@Composable
private fun V5ChatBubble(message: String, fromStudent: Boolean) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val maximumBubbleWidth = maxWidth - if (fromStudent) 44.dp else 38.dp
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = if (fromStudent) Arrangement.End else Arrangement.Start,
            verticalAlignment = Alignment.Top,
        ) {
            if (!fromStudent) {
                Surface(shape = RoundedCornerShape(7.dp), color = Color(0xFFEDF4FA), modifier = Modifier.size(24.dp)) {
                    Box(contentAlignment = Alignment.Center) { Text("知", color = Color(0xFF285E91), fontSize = 10.sp, fontWeight = FontWeight.Bold, fontFamily = NativeV5Tokens.Font) }
                }
            }
            Surface(
                shape = RoundedCornerShape(if (fromStudent) 16.dp else 14.dp),
                color = if (fromStudent) Color(0xFFEAF4FF) else Color.White,
                border = androidx.compose.foundation.BorderStroke(1.dp, if (fromStudent) Color(0xFFD7E8FA) else Color(0xFFE4E8ED)),
                modifier = Modifier.padding(start = if (fromStudent) 0.dp else 8.dp).widthIn(max = maximumBubbleWidth),
            ) {
                Column(Modifier.padding(11.dp)) {
                    Text(message, color = NativeV5Tokens.Ink, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = NativeV5Tokens.Font)
                }
            }
        }
    }
}

/**
 * Current-L2 content relationships are deliberately isolated from the
 * student's long-term knowledge vault.  The two modes express the same
 * content package with different semantics: hierarchy vs. cross-links.
 */
@Composable
private fun ContentConceptCanvas(
    mapMode: Int,
    modifier: Modifier,
    expanded: Boolean = false,
    onOpenNode: (String) -> Unit = {},
) {
    // 内容图只描述当前 L2 内容包：与长期知识库完全分离。节点、连线与拖拽
    // 共用 positions，避免此前 Canvas 和可点击元素各自计算造成的悬空连线。
    val shape = RoundedCornerShape(if (expanded) 18.dp else 12.dp)
    // Match the approved V5 AI-and-digital-media content example.  This canvas
    // belongs to the current content package, not to the unrelated first-
    // person urban-space example that previously leaked into this route.
    val labels = if (mapMode == 0) {
        listOf("生成式 AI", "媒体创作", "版权伦理", "学习数据", "虚拟演员")
    } else {
        listOf("生成式 AI", "创作流程", "版权权利", "内容可信度", "数字人")
    }
    val defaults = if (mapMode == 0) listOf(.50f to .18f, .22f to .52f, .50f to .52f, .78f to .52f, .50f to .82f)
    else listOf(.50f to .48f, .20f to .25f, .80f to .25f, .20f to .76f, .80f to .76f)
    // 普通内容页和全屏内容页是两次独立 Composition。不能把坐标仅放在
    // remember(mapMode, expanded) 中，否则进入全屏会回到默认位置，连线也会
    // 看起来和刚刚拖动的节点脱节。使用归一化坐标持久化，两个画布按各自尺寸
    // 重算同一个位置与同一组边缘锚点。
    val context = LocalContext.current
    val contentLayoutPreferences = remember(context) {
        context.getSharedPreferences("v5_content_graph_layout", android.content.Context.MODE_PRIVATE)
    }
    val positions = remember(mapMode) {
        mutableStateListOf<Pair<Float, Float>>().also { layout ->
            defaults.forEachIndexed { index, fallback ->
                val stored = contentLayoutPreferences
                    .getString("content:$mapMode:$index:position", null)
                    ?.split(',')
                val restored = stored?.getOrNull(0)?.toFloatOrNull()?.let { x ->
                    stored.getOrNull(1)?.toFloatOrNull()?.let { y -> x to y }
                }
                layout += restored ?: fallback
            }
        }
    }
    val edges = if (mapMode == 0) listOf(0 to 1, 0 to 2, 0 to 3, 2 to 4) else listOf(0 to 1, 0 to 2, 0 to 3, 0 to 4, 1 to 4, 2 to 3)
    val density = LocalDensity.current
    BoxWithConstraints(modifier = modifier.clip(shape).background(Color(0xFFFBFDFF)).border(1.dp, Color(0xFFDDE7F0), shape)) {
        val nodeWidth = if (expanded) 104.dp else 82.dp
        val nodeHeight = if (expanded) 42.dp else 32.dp
        val nodeWidthPx = with(density) { nodeWidth.toPx() }
        val nodeHeightPx = with(density) { nodeHeight.toPx() }
        Canvas(Modifier.fillMaxSize()) {
            val centers = positions.map { androidx.compose.ui.geometry.Offset(size.width * it.first, size.height * it.second) }
            fun edge(from: Int, to: Int, color: Color) {
                val a = centers[from]; val b = centers[to]
                val dx = b.x - a.x; val dy = b.y - a.y
                val length = kotlin.math.sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
                val ux = dx / length; val uy = dy / length
                val distance = minOf(nodeWidthPx / 2f / kotlin.math.abs(ux).coerceAtLeast(.001f), nodeHeightPx / 2f / kotlin.math.abs(uy).coerceAtLeast(.001f))
                drawLine(color.copy(alpha = .78f), androidx.compose.ui.geometry.Offset(a.x + ux * distance, a.y + uy * distance), androidx.compose.ui.geometry.Offset(b.x - ux * distance, b.y - uy * distance), 1.4.dp.toPx(), StrokeCap.Round)
            }
            edges.forEachIndexed { index, (from, to) -> edge(from, to, if (index == edges.lastIndex && mapMode == 0) Color(0xFF1F9D8B) else NativeV5Tokens.Accent) }
        }
        positions.forEachIndexed { index, (x, y) ->
            Surface(
                modifier = Modifier
                    .offset(x = maxWidth * x - nodeWidth / 2, y = maxHeight * y - nodeHeight / 2)
                    .width(nodeWidth).height(nodeHeight)
                    .pointerInput(mapMode, index) {
                        detectDragGestures(
                            onDrag = { change, delta ->
                                change.consume()
                                val next = (
                                    (positions[index].first + delta.x / size.width).coerceIn(.10f, .90f) to
                                        (positions[index].second + delta.y / size.height).coerceIn(.10f, .90f)
                                    )
                                positions[index] = next
                                contentLayoutPreferences.edit()
                                    .putString("content:$mapMode:$index:position", "${next.first},${next.second}")
                                    .apply()
                            },
                            onDragEnd = {},
                        )
                    }
                    .clickable { onOpenNode(labels[index]) },
                shape = RoundedCornerShape(if (index == 0) 10.dp else 8.dp),
                color = if (index == 0) Color(0xFF1D2024) else Color.White,
                border = if (index == 0) null else androidx.compose.foundation.BorderStroke(1.dp, if (mapMode == 0) Color(0xFF78B9A9) else Color(0xFFE2AE5A)),
                shadowElevation = 2.dp,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(labels[index], color = if (index == 0) Color.White else NativeV5Tokens.Ink, fontSize = if (expanded) 12.sp else 9.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 5.dp))
                }
            }
        }
    }
}

@Composable
private fun V5GraphCanvas(
    modifier: Modifier,
    expanded: Boolean = false,
    onOpenNode: ((KnowledgeGraphNode) -> Unit)? = null,
    onCreateChild: ((KnowledgeGraphNode?) -> Unit)? = null,
) {
    val context = LocalContext.current
    val repository = remember { MobileAppServices.knowledgeVault(context) }
    val snapshot by repository.observeGraph().collectAsState(initial = cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot.empty())
    val sessionStore = remember { AndroidMobileSessionStore(context.applicationContext) }
    val session by sessionStore.current.collectAsState()
    val scope = rememberCoroutineScope()
    val shape = RoundedCornerShape(if (expanded) 18.dp else 12.dp)
    var creatingChildFor by remember { mutableStateOf<KnowledgeGraphNode?>(null) }
    var editingNode by remember { mutableStateOf<KnowledgeGraphNode?>(null) }
    var creatingRoot by remember { mutableStateOf(false) }
    // A normalized layout is persisted once per node.  Both the compact and
    // full canvas read it, so a dragged node cannot leave its edge or + anchor
    // behind when the student re-enters a different canvas size.
    val layoutPreferences = remember { context.getSharedPreferences("v5_graph_layout", android.content.Context.MODE_PRIVATE) }
    val nodeKey = snapshot.nodes.joinToString("|") { it.id.value }
    val nodePositions = remember(nodeKey) {
        mutableStateMapOf<KnowledgeGraphNodeId, Pair<Float, Float>>().also { layout ->
            snapshot.nodes.forEachIndexed { index, node ->
                val saved = layoutPreferences.getString("${node.id.value}:position", null)?.split(',')
                val fallback = if (index == 0) .50f to .50f else {
                    val angle = (index - 1) * (2.0 * Math.PI / (snapshot.nodes.size - 1).coerceAtLeast(1)) - Math.PI / 2.0
                    (.50f + .31f * kotlin.math.cos(angle).toFloat()) to (.50f + .31f * kotlin.math.sin(angle).toFloat())
                }
                layout[node.id] = saved?.getOrNull(0)?.toFloatOrNull()?.let { x -> saved.getOrNull(1)?.toFloatOrNull()?.let { y -> x to y } } ?: fallback
            }
        }
    }
    val nodes = snapshot.nodes
    BoxWithConstraints(modifier = modifier.clip(shape).background(Color(0xFFFBFDFF)).border(1.dp, Color(0xFFDDE7F0), shape)) {
        val nodeWidth = if (expanded) 104.dp else 84.dp
        val nodeHeight = if (expanded) 42.dp else 36.dp
        val coreWidth = if (expanded) 104.dp else 92.dp
        val coreHeight = if (expanded) 44.dp else 38.dp
        Canvas(Modifier.fillMaxSize()) {
            val positions = nodes.associate { node ->
                val (x, y) = nodePositions[node.id] ?: (.50f to .50f)
                node.id to androidx.compose.ui.geometry.Offset(size.width * x, size.height * y)
            }
            snapshot.edges.filter { it.from in positions && it.to in positions }.forEach { edge ->
                val from = positions.getValue(edge.from)
                val to = positions.getValue(edge.to)
                val dx = to.x - from.x
                val dy = to.y - from.y
                val length = kotlin.math.sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
                val ux = dx / length
                val uy = dy / length
                fun rectangleEdgeDistance(coreNode: Boolean): Float {
                    val halfWidth = (if (coreNode) coreWidth else nodeWidth).toPx() / 2f
                    val halfHeight = (if (coreNode) coreHeight else nodeHeight).toPx() / 2f
                    val horizontal = if (kotlin.math.abs(ux) < .0001f) Float.POSITIVE_INFINITY else halfWidth / kotlin.math.abs(ux)
                    val vertical = if (kotlin.math.abs(uy) < .0001f) Float.POSITIVE_INFINITY else halfHeight / kotlin.math.abs(uy)
                    return minOf(horizontal, vertical)
                }
                val fromDistance = rectangleEdgeDistance(edge.from == nodes.firstOrNull()?.id)
                val toDistance = rectangleEdgeDistance(edge.to == nodes.firstOrNull()?.id)
                drawLine(
                    Color(0xFF7BB6E5),
                    androidx.compose.ui.geometry.Offset(from.x + ux * fromDistance, from.y + uy * fromDistance),
                    androidx.compose.ui.geometry.Offset(to.x - ux * toDistance, to.y - uy * toDistance),
                    1.5.dp.toPx(),
                    StrokeCap.Round,
                )
            }
            var gridX = 10.dp.toPx()
            while (gridX < size.width) {
                var gridY = 10.dp.toPx()
                while (gridY < size.height) {
                    drawCircle(Color(0x1F3069A2), radius = .9.dp.toPx(), center = androidx.compose.ui.geometry.Offset(gridX, gridY))
                    gridY += 18.dp.toPx()
                }
                gridX += 18.dp.toPx()
            }
        }
        if (nodes.isEmpty()) {
            // 空库不渲染预置概念或示例关系，避免把产品原型误当作学生知识。
            // 唯一入口会创建真实根节点，并由仓储和事件日志持久化。
            Column(
                modifier = Modifier.fillMaxSize().padding(18.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text("知识全览尚无节点", color = NativeV5Tokens.Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font)
                Text("新建根节点后，可继续添加子节点、双向链接和笔记。", color = NativeV5Tokens.Muted, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = NativeV5Tokens.Font, modifier = Modifier.padding(top = 6.dp))
                V5PrimaryButton("新建根节点", Modifier.fillMaxWidth().padding(top = 12.dp)) { onCreateChild?.invoke(null) ?: run { creatingRoot = true } }
            }
        } else {
            nodes.forEachIndexed { index, node ->
                val (x, y) = nodePositions[node.id] ?: (.50f to .50f)
                val width = if (index == 0) coreWidth else nodeWidth
                val height = if (index == 0) coreHeight else nodeHeight
                val nodeModifier = Modifier
                    .align(Alignment.TopStart)
                    .offset(x = maxWidth * x - width / 2, y = maxHeight * y - height / 2)
                    .pointerInput(node.id, maxWidth, maxHeight) {
                        detectDragGestures(onDrag = { change, delta ->
                            change.consume()
                            val current = nodePositions[node.id] ?: (.50f to .50f)
                            val next = ((current.first + delta.x / size.width).coerceIn(.08f, .92f) to (current.second + delta.y / size.height).coerceIn(.08f, .92f))
                            nodePositions[node.id] = next
                            layoutPreferences.edit().putString("${node.id.value}:position", "${next.first},${next.second}").apply()
                        })
                    }
                V5GraphNode(label = node.label, core = index == 0, width = width, height = height, modifier = nodeModifier, onOpen = { onOpenNode?.invoke(node) ?: run { editingNode = node } }, onAdd = { onCreateChild?.invoke(node) ?: run { creatingChildFor = node } })
            }
        }
    }
    editingNode?.let { node ->
        var label by remember(node.id) { mutableStateOf(node.label) }
        var note by remember(node.id) { mutableStateOf(node.note) }
        AlertDialog(
            onDismissRequest = { editingNode = null },
            title = { Text(node.label, fontFamily = NativeV5Tokens.Font) },
            text = { Column { OutlinedTextField(value = label, onValueChange = { label = it }, label = { Text("节点名称", fontFamily = NativeV5Tokens.Font) }, singleLine = true); OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("节点笔记", fontFamily = NativeV5Tokens.Font) }, minLines = 3) } },
            confirmButton = { TextButton(enabled = label.isNotBlank(), onClick = { scope.launch { if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) repository.confirmSuggestion(node.id) else repository.updateStudentNode(node.id, label.trim(), note); editingNode = null } }) { Text(if (node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) "确认建议" else "保存", fontFamily = NativeV5Tokens.Font) } },
            dismissButton = { Row { if (node.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED) TextButton(onClick = { scope.launch { repository.removeNode(node.id); editingNode = null } }) { Text("删除节点", fontFamily = NativeV5Tokens.Font) }; TextButton(onClick = { editingNode = null }) { Text("取消", fontFamily = NativeV5Tokens.Font) } } },
        )
    }
    if (creatingRoot || creatingChildFor != null) {
        val parent = creatingChildFor
        var childName by remember(parent?.id) { mutableStateOf("") }
        var childNote by remember(parent?.id) { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { creatingRoot = false; creatingChildFor = null },
            title = { Text(if (parent == null) "新建知识节点" else "为“${parent.label}”新建子节点", fontFamily = NativeV5Tokens.Font) },
            text = { Column { OutlinedTextField(value = childName, onValueChange = { childName = it }, label = { Text("节点名称") }, singleLine = true); OutlinedTextField(value = childNote, onValueChange = { childNote = it }, label = { Text("节点笔记") }, minLines = 2) } },
            confirmButton = { TextButton(enabled = childName.isNotBlank(), onClick = { scope.launch { val activeSession = session ?: sessionStore.open(); val child = repository.createStudentNode(StudentKnowledgeNodeDraft(KnowledgeGraphNodeId("student:" + UUID.randomUUID()), childName.trim(), activeSession.id, parent?.evidenceRefs.orEmpty(), childNote)); parent?.let { repository.createStudentEdge(StudentKnowledgeEdgeDraft(KnowledgeGraphEdgeId("student-edge:" + UUID.randomUUID()), it.id, child.id, KnowledgeRelationship.PART_OF)) }; creatingRoot = false; creatingChildFor = null } }) { Text("创建", fontFamily = NativeV5Tokens.Font) } },
            dismissButton = { TextButton(onClick = { creatingRoot = false; creatingChildFor = null }) { Text("取消", fontFamily = NativeV5Tokens.Font) } },
        )
    }
}

@Composable
private fun V5GraphNode(
    label: String,
    width: androidx.compose.ui.unit.Dp,
    height: androidx.compose.ui.unit.Dp,
    modifier: Modifier = Modifier,
    core: Boolean = false,
    onOpen: () -> Unit,
    onAdd: () -> Unit,
) {
    // 节点的几何边界、连线终点和“+”锚点共用 width。+ 的中心落在右缘，
    // 不再因额外的父容器宽度而漂浮在节点外侧。
    Box(modifier = modifier.width(width).height(height)) {
        Surface(
            shape = RoundedCornerShape(if (core) 9.dp else 8.dp),
            color = if (core) Color(0xFF1D2024) else Color.White,
            border = if (core) null else androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFD9E0E7)),
            shadowElevation = if (core) 3.dp else 2.dp,
            modifier = Modifier.width(width).height(height).clickable(onClick = onOpen),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(label, color = if (core) Color.White else NativeV5Tokens.Ink, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, fontFamily = NativeV5Tokens.Font, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 6.dp))
            }
        }
        Surface(
            shape = RoundedCornerShape(50.dp),
            color = Color(0xFFFBFDFF),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFA9C6DF)),
            modifier = Modifier.align(Alignment.CenterEnd).offset(x = 9.dp).size(18.dp).clip(RoundedCornerShape(50.dp)).clickable(onClick = onAdd),
        ) {
            Box(contentAlignment = Alignment.Center) { V5LineIcon(V5Icon.ADD, tint = NativeV5Tokens.Accent, contentDescription = "在$label 下新建子节点", modifier = Modifier.size(12.dp)) }
        }
    }
}

@Composable
private fun V5AnalyticsCanvas(chart: V5Chart, analysisFilterIndex: Int, modifier: Modifier) {
    Canvas(
        modifier = modifier.clip(RoundedCornerShape(12.dp)).background(Color(0xFFFBFBFC))
            .border(1.dp, Color(0xFFE7E7EA), RoundedCornerShape(12.dp)),
    ) {
        val w = size.width
        val h = size.height
        val left = 38.dp.toPx()
        val top = 22.dp.toPx()
        val right = w - 22.dp.toPx()
        val bottom = h - 34.dp.toPx()
        val axis = Color(0xFFC9CED6)
        val blue = NativeV5Tokens.Accent
        val teal = Color(0xFF1F9D8B)
        val amber = Color(0xFFF0A12B)
        val filter = analysisFilterIndex.coerceIn(V5_ANALYSIS_FILTERS.indices)
        fun point(x: Float, y: Float) = androidx.compose.ui.geometry.Offset(left + (right - left) * x, top + (bottom - top) * y)

        when (chart) {
            V5Chart.VENN -> {
                val radius = minOf(w, h) * listOf(.20f, .17f, .18f, .15f)[filter]
                drawCircle(blue.copy(alpha = .23f), radius, androidx.compose.ui.geometry.Offset(w * .43f, h * .52f))
                drawCircle(teal.copy(alpha = .23f), radius, androidx.compose.ui.geometry.Offset(w * .57f, h * .52f))
                drawCircle(blue, radius, androidx.compose.ui.geometry.Offset(w * .43f, h * .52f), style = Stroke(1.5.dp.toPx()))
                drawCircle(teal, radius, androidx.compose.ui.geometry.Offset(w * .57f, h * .52f), style = Stroke(1.5.dp.toPx()))
            }
            V5Chart.SET -> {
                val outer = androidx.compose.ui.geometry.Rect(left, top + 10.dp.toPx(), right, bottom)
                drawRoundRect(blue.copy(alpha = .07f), topLeft = outer.topLeft, size = outer.size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(12.dp.toPx(), 12.dp.toPx()))
                drawRoundRect(blue.copy(alpha = .65f), topLeft = outer.topLeft, size = outer.size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(12.dp.toPx(), 12.dp.toPx()), style = Stroke(1.5.dp.toPx()))
                val inner = listOf(
                    androidx.compose.ui.geometry.Rect(w * .32f, h * .36f, w * .68f, h * .70f),
                    androidx.compose.ui.geometry.Rect(w * .38f, h * .40f, w * .62f, h * .64f),
                    androidx.compose.ui.geometry.Rect(w * .26f, h * .42f, w * .62f, h * .69f),
                    androidx.compose.ui.geometry.Rect(w * .45f, h * .34f, w * .73f, h * .60f),
                )[filter]
                drawRoundRect(teal.copy(alpha = .16f), topLeft = inner.topLeft, size = inner.size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(10.dp.toPx(), 10.dp.toPx()))
                drawRoundRect(teal, topLeft = inner.topLeft, size = inner.size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(10.dp.toPx(), 10.dp.toPx()), style = Stroke(1.5.dp.toPx()))
            }
            V5Chart.SCATTER -> {
                drawLine(axis, androidx.compose.ui.geometry.Offset(left, bottom), androidx.compose.ui.geometry.Offset(right, bottom), 1.dp.toPx())
                drawLine(axis, androidx.compose.ui.geometry.Offset(left, top), androidx.compose.ui.geometry.Offset(left, bottom), 1.dp.toPx())
                val points = listOf(
                    listOf(.12f to .76f, .28f to .57f, .48f to .65f, .69f to .34f, .87f to .14f),
                    listOf(.18f to .69f, .43f to .51f, .71f to .28f),
                    listOf(.23f to .62f, .50f to .43f, .82f to .22f),
                    listOf(.31f to .57f, .62f to .33f),
                )[filter]
                points.forEachIndexed { index, (x, y) -> drawCircle(if (index % 2 == 0) blue else teal, 5.dp.toPx(), point(x, y)) }
            }
            V5Chart.PIE -> {
                val diameter = minOf(w, h) * .56f
                val start = androidx.compose.ui.geometry.Offset(w * .5f - diameter / 2, h * .5f - diameter / 2)
                val chartSize = androidx.compose.ui.geometry.Size(diameter, diameter)
                var angle = -90f
                val sweeps = listOf(
                    listOf(150f, 105f, 65f, 40f),
                    listOf(125f, 125f, 70f, 40f),
                    listOf(180f, 80f, 60f, 40f),
                    listOf(105f, 145f, 75f, 35f),
                )[filter]
                listOf(blue, teal, amber, Color(0xFF7A8CA5)).zip(sweeps).forEach { (color, sweep) ->
                    drawArc(color, angle, sweep, true, start, chartSize)
                    angle += sweep
                }
                drawCircle(Color(0xFFFBFBFC), diameter * .23f, center)
            }
            V5Chart.BAR -> {
                drawLine(axis, androidx.compose.ui.geometry.Offset(left, bottom), androidx.compose.ui.geometry.Offset(right, bottom), 1.dp.toPx())
                listOf(
                    listOf(.35f, .70f, .48f, .82f),
                    listOf(.26f, .55f, .41f, .66f),
                    listOf(.72f, .44f, .60f, .33f),
                    listOf(.18f, .63f, .37f, .74f),
                )[filter].forEachIndexed { index, value ->
                    val barWidth = (right - left) / 8f
                    val x = left + barWidth * (index * 2 + 1)
                    val y = bottom - (bottom - top) * value
                    drawRoundRect(if (index % 2 == 0) blue else teal, topLeft = androidx.compose.ui.geometry.Offset(x, y), size = androidx.compose.ui.geometry.Size(barWidth, bottom - y), cornerRadius = androidx.compose.ui.geometry.CornerRadius(4.dp.toPx(), 4.dp.toPx()))
                }
            }
            V5Chart.LINE -> {
                drawLine(axis, androidx.compose.ui.geometry.Offset(left, bottom), androidx.compose.ui.geometry.Offset(right, bottom), 1.dp.toPx())
                drawLine(axis, androidx.compose.ui.geometry.Offset(left, top), androidx.compose.ui.geometry.Offset(left, bottom), 1.dp.toPx())
                val points = listOf(
                    listOf(.0f to .76f, .24f to .69f, .43f to .46f, .60f to .53f, .77f to .35f, 1f to .18f),
                    listOf(.0f to .61f, .30f to .56f, .56f to .42f, .78f to .31f, 1f to .26f),
                    listOf(.0f to .74f, .25f to .52f, .51f to .58f, .76f to .27f, 1f to .20f),
                    listOf(.0f to .81f, .28f to .67f, .56f to .47f, .78f to .55f, 1f to .36f),
                )[filter].map { point(it.first, it.second) }
                val path = Path().apply { moveTo(points.first().x, points.first().y); points.drop(1).forEach { lineTo(it.x, it.y) } }
                drawPath(path, blue, style = Stroke(3.dp.toPx(), cap = StrokeCap.Round))
                points.forEach { drawCircle(Color.White, 5.dp.toPx(), it); drawCircle(blue, 3.dp.toPx(), it) }
            }
        }
    }
}

@Composable
private fun V5LineIcon(
    icon: V5Icon,
    tint: Color = NativeV5Tokens.Ink,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier.semantics { this.contentDescription = contentDescription }) {
        val stroke = 1.65.dp.toPx()
        val w = size.width
        val h = size.height
        fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(tint, androidx.compose.ui.geometry.Offset(w * x1, h * y1), androidx.compose.ui.geometry.Offset(w * x2, h * y2), stroke, StrokeCap.Round)
        when (icon) {
            V5Icon.MENU -> { line(.18f, .28f, .82f, .28f); line(.18f, .50f, .82f, .50f); line(.18f, .72f, .82f, .72f) }
            V5Icon.BACK -> { line(.70f, .18f, .30f, .50f); line(.30f, .50f, .70f, .82f) }
            V5Icon.FORWARD -> { line(.30f, .18f, .70f, .50f); line(.70f, .50f, .30f, .82f) }
            V5Icon.DISCOVER -> { drawCircle(tint, size.minDimension * .34f, center = center, style = Stroke(stroke)); drawCircle(tint, size.minDimension * .11f, center = center) }
            V5Icon.ANALYTICS -> { line(.22f, .73f, .22f, .28f); line(.22f, .73f, .78f, .73f); line(.34f, .62f, .47f, .47f); line(.47f, .47f, .59f, .55f); line(.59f, .55f, .76f, .27f) }
            V5Icon.AGENT -> { drawRoundRect(tint, size = androidx.compose.ui.geometry.Size(w * .56f, h * .52f), topLeft = androidx.compose.ui.geometry.Offset(w * .22f, h * .22f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * .12f, w * .12f), style = Stroke(stroke)); drawCircle(tint, w * .045f, center = androidx.compose.ui.geometry.Offset(w * .40f, h * .48f)); drawCircle(tint, w * .045f, center = androidx.compose.ui.geometry.Offset(w * .60f, h * .48f)); line(.42f, .66f, .58f, .66f) }
            V5Icon.CONNECTION -> { drawCircle(tint, w * .12f, center = androidx.compose.ui.geometry.Offset(w * .34f, h * .50f), style = Stroke(stroke)); drawCircle(tint, w * .12f, center = androidx.compose.ui.geometry.Offset(w * .66f, h * .50f), style = Stroke(stroke)); line(.43f, .50f, .57f, .50f) }
            V5Icon.ADD -> { line(.50f, .20f, .50f, .80f); line(.20f, .50f, .80f, .50f) }
            V5Icon.EXPAND -> { line(.18f, .42f, .18f, .18f); line(.18f, .18f, .42f, .18f); line(.82f, .42f, .82f, .18f); line(.82f, .18f, .58f, .18f); line(.18f, .58f, .18f, .82f); line(.18f, .82f, .42f, .82f); line(.82f, .58f, .82f, .82f); line(.82f, .82f, .58f, .82f) }
            V5Icon.ATTACH -> { drawCircle(tint, size.minDimension * .19f, center = androidx.compose.ui.geometry.Offset(w * .45f, h * .54f), style = Stroke(stroke)); line(.56f, .28f, .76f, .48f); line(.76f, .48f, .53f, .71f) }
            V5Icon.NETWORK -> { drawArc(tint, 210f, 120f, false, topLeft = androidx.compose.ui.geometry.Offset(w * .16f, h * .16f), size = androidx.compose.ui.geometry.Size(w * .68f, h * .68f), style = Stroke(stroke)); drawArc(tint, 210f, 120f, false, topLeft = androidx.compose.ui.geometry.Offset(w * .30f, h * .30f), size = androidx.compose.ui.geometry.Size(w * .40f, h * .40f), style = Stroke(stroke)); drawCircle(tint, w * .06f, center = androidx.compose.ui.geometry.Offset(w * .50f, h * .70f)) }
            V5Icon.SEND -> { line(.18f, .18f, .84f, .50f); line(.84f, .50f, .18f, .82f); line(.18f, .18f, .42f, .50f); line(.42f, .50f, .18f, .82f) }
        }
    }
}

public object NativeV5Tokens {
    public val Canvas: Color = Color(0xFFF2F7FC)
    public val Ink: Color = Color(0xFF1D1D1F)
    public val Muted: Color = Color(0xFF6E6E73)
    public val IconMuted: Color = Color(0xFF7C818C)
    public val Accent: Color = Color(0xFF1877E6)
    public val Quiet: Color = Color(0xFFF0F4F8)
    public val Positive: Color = Color(0xFF16804A)
    public val PositiveSoft: Color = Color(0xFFEAF6EE)
    public val Warning: Color = Color(0xFF9F6200)
    public val WarningSoft: Color = Color(0xFFFFF4DC)
    public val Font: FontFamily = V5Typography.Family
}
