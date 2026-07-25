package cn.zhixingzhixue.learning.application

import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.DeviceConnection
import cn.zhixingzhixue.learning.domain.DeviceId
import cn.zhixingzhixue.learning.domain.KnowledgePointCandidate
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.MobileLearningSession
import cn.zhixingzhixue.learning.domain.StudentReceipt
import cn.zhixingzhixue.learning.domain.SyncAnchor
import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjection
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdge
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdgeId
import cn.zhixingzhixue.learning.domain.MobileProfileUpdate
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
import cn.zhixingzhixue.learning.domain.StudentKnowledgeNodeDraft
import cn.zhixingzhixue.learning.domain.StudentKnowledgeEdgeDraft
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import cn.zhixingzhixue.learning.domain.AgentConversationMessage
import cn.zhixingzhixue.learning.domain.AgentContextReference
import cn.zhixingzhixue.learning.domain.AgentResourceAttachment
import cn.zhixingzhixue.learning.domain.AgentKnowledgeReference
import cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import java.time.OffsetDateTime

public enum class MediaTransportStatus {
    IDLE,
    WAITING_FOR_USER_PERMISSION,
    STREAMING,
    DEGRADED,
    STOPPED,
    ERROR
}

public data class MediaTransportState(
    val status: MediaTransportStatus,
    val sessionId: MobileSessionId?,
    val captureId: CaptureId?,
    val startedAt: OffsetDateTime?,
    val deviceAudioAvailable: Boolean,
    val activeConsumerCount: Int,
    val errorCode: String?
)

/** Business code sees no RTSP, Android Intent, MediaProjection, or platform rule. */
public interface MediaTransportPort {
    public val state: StateFlow<MediaTransportState>
}

public interface CandidateRepository {
    public suspend fun upsert(candidate: KnowledgePointCandidate)
    public fun observe(sessionId: MobileSessionId): Flow<List<KnowledgePointCandidate>>
}

/** Phone cards are immutable candidate evidence envelopes, kept separate from inferred profiles. */
public interface CandidateCardRepository {
    public suspend fun upsert(card: CandidateCard)
    public fun observe(): Flow<List<CandidateCard>>
}

/**
 * The phone's local, evidence-backed knowledge vault. PC result delivery and
 * Android persistence are adapters; graph policy stays inside the domain.
 */
public interface KnowledgeGraphRepository {
    public fun observeGraph(): Flow<KnowledgeGraphSnapshot>
    public fun observeProfile(): Flow<List<MobileProfileUpdate>>
    public suspend fun apply(result: PcKnowledgeAnalysisResult): KnowledgeGraphProjection
    /** The mobile note editor writes only explicit student actions to the local vault. */
    public suspend fun createStudentNode(draft: StudentKnowledgeNodeDraft): KnowledgeGraphNode
    public suspend fun updateStudentNode(nodeId: KnowledgeGraphNodeId, label: String, note: String): KnowledgeGraphNode?
    public suspend fun confirmSuggestion(nodeId: KnowledgeGraphNodeId): KnowledgeGraphNode?
    public suspend fun removeNode(nodeId: KnowledgeGraphNodeId): Boolean
    public suspend fun createStudentEdge(draft: StudentKnowledgeEdgeDraft): KnowledgeGraphEdge
    public suspend fun removeEdge(edgeId: KnowledgeGraphEdgeId): Boolean
}

public interface SessionPort {
    public val current: StateFlow<MobileLearningSession?>
    public suspend fun open(): MobileLearningSession
    public suspend fun close(): Unit
}

public interface ReceiptPort {
    public suspend fun record(receipt: StudentReceipt)
}

/** Local-first journal for voluntary L3/L4 student writing. */
public interface LearningResponsePort {
    public fun observe(resultId: String, contentId: String): Flow<List<StudentLearningResponse>>
    public suspend fun record(response: StudentLearningResponse)
}

/** The application checks content-package and voluntary-stage eligibility before recording writing. */
public interface LearningResponseEligibilityPort {
    public suspend fun canRecord(response: StudentLearningResponse): Boolean
}

public class RecordStudentLearningResponse(
    private val eligibility: LearningResponseEligibilityPort,
    private val responses: LearningResponsePort,
) {
    public suspend fun record(response: StudentLearningResponse) {
        require(eligibility.canRecord(response)) { "learning_response_not_eligible" }
        responses.record(response)
    }
}

/**
 * Local conversation and attachment queue for the independent agent workspace.
 * It intentionally exposes no model call: networking, search, parsing and file
 * generation are future outer adapters with explicit remote-run contracts.
 */
public interface AgentWorkspacePort {
    public fun observe(): Flow<AgentWorkspaceSnapshot>
    public suspend fun beginEmptyConversation()
    public suspend fun replaceContextReferences(references: List<AgentContextReference>)
    public suspend fun replaceKnowledgeReferences(references: List<AgentKnowledgeReference>)
    public suspend fun appendMessage(message: AgentConversationMessage)
    public suspend fun addResources(resources: List<AgentResourceAttachment>)
    public suspend fun updateResource(resource: AgentResourceAttachment)
    public suspend fun removeResource(resourceId: String)
}

public data class CandidateNotice(
    val notificationId: Int,
    val candidate: CandidateCard,
    val title: String,
    val message: String
)

public interface StudentNotificationPort {
    /** Shows a heads-up eligible notice; the OS and student settings remain authoritative. */
    public suspend fun show(notice: CandidateNotice)
}

public interface DeviceConnectionPort {
    public fun observe(): Flow<List<DeviceConnection>>
    public suspend fun disconnect(deviceId: DeviceId)
}

public interface TimeSyncPort {
    public suspend fun sample(peer: DeviceId): SyncAnchor
}

public interface TeacherExportContributionPort {
    /** Exports a versioned, white-listed contribution; never a teacher UI or network login. */
    public suspend fun exportFor(sessionId: MobileSessionId): String
}
