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
import cn.zhixingzhixue.learning.domain.MobileProfileUpdate
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
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
}

public interface SessionPort {
    public val current: StateFlow<MobileLearningSession?>
    public suspend fun open(): MobileLearningSession
    public suspend fun close(): Unit
}

public interface ReceiptPort {
    public suspend fun record(receipt: StudentReceipt)
}

public data class CandidateNotice(
    val notificationId: Int,
    val candidate: KnowledgePointCandidate,
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
