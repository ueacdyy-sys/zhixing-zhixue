package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime

/** First capture layer: user-authorized display-level continuous media. */
public enum class DisplayCaptureStatus {
    NOT_STARTED,
    STREAMING,
    PAUSED,
    STOPPED,
    ERROR,
}

public data class DisplayLevelCapture(
    val captureId: CaptureId,
    val consentedAt: OffsetDateTime,
    val status: DisplayCaptureStatus,
)

/**
 * Second capture layer: a replaceable, explicitly scoped connector for public
 * streaming or graphic-content sources. It never replaces display consent.
 */
public enum class PublicContentSourceCategory {
    STREAMING_OR_GRAPHIC,
}

public enum class DirectConnectorStatus {
    ACTIVE,
    DEGRADED,
    UNAVAILABLE,
}

public data class PlatformDirectConnector(
    val connectorId: String,
    val sourceCategory: PublicContentSourceCategory,
    val status: DirectConnectorStatus,
) {
    init {
        require(connectorId.isNotBlank()) { "platform_connector_id_required" }
    }
}

/** Both capture layers belong to one student-started mobile session. */
public data class DualLayerCaptureSession(
    val sessionId: MobileSessionId,
    val displayCapture: DisplayLevelCapture,
    val directConnectors: List<PlatformDirectConnector>,
) {
    init {
        require(displayCapture.status == DisplayCaptureStatus.STREAMING) {
            "display_level_capture_must_be_streaming"
        }
        require(directConnectors.map { it.connectorId }.distinct().size == directConnectors.size) {
            "platform_connector_ids_must_be_unique"
        }
    }
}

public enum class PcAnalysisClassification {
    CANDIDATE_ONLY,
}

public enum class KnowledgeRelationship {
    MENTIONS_CONCEPT,
}

/**
 * A PC-provided association is evidence-linked, revisable and deliberately
 * not a statement about student ability, mastery or psychological state.
 */
public data class KnowledgeAssociation(
    val topic: String,
    val subjectTag: String,
    val relationship: KnowledgeRelationship,
    val confidence: Double,
    val evidenceRefs: List<LocalEvidenceRef>,
) {
    init {
        require(topic.isNotBlank()) { "knowledge_topic_required" }
        require(subjectTag.isNotBlank()) { "knowledge_subject_required" }
        require(confidence in 0.0..1.0) { "knowledge_confidence_out_of_range" }
        require(evidenceRefs.isNotEmpty()) { "knowledge_association_evidence_required" }
    }
}

/** Formal PC-to-phone result contract, independent of ADB/debug broadcasts. */
public data class PcKnowledgeAnalysisResult(
    val resultId: String,
    val sessionId: MobileSessionId,
    val visitId: String,
    val createdAt: OffsetDateTime,
    val evidenceRefs: List<LocalEvidenceRef>,
    val associations: List<KnowledgeAssociation>,
    val classification: PcAnalysisClassification = PcAnalysisClassification.CANDIDATE_ONLY,
) {
    init {
        require(resultId.isNotBlank()) { "pc_analysis_result_id_required" }
        require(visitId.isNotBlank()) { "pc_analysis_visit_required" }
        require(evidenceRefs.distinct().size == evidenceRefs.size) { "pc_analysis_evidence_must_be_unique" }
        require(evidenceRefs.isNotEmpty()) { "pc_analysis_evidence_required" }
        require(classification == PcAnalysisClassification.CANDIDATE_ONLY) {
            "pc_analysis_must_remain_candidate_only"
        }
    }
}

@JvmInline
public value class KnowledgeGraphNodeId(public val value: String)

@JvmInline
public value class KnowledgeGraphEdgeId(public val value: String)

public enum class KnowledgeGraphNodeType {
    MEDIA_EVIDENCE,
    INTEREST_TOPIC,
    SUBJECT_KNOWLEDGE,
    LEARNING_RESOURCE,
    STUDENT_ACTION,
}

public data class KnowledgeGraphNode(
    val id: KnowledgeGraphNodeId,
    val type: KnowledgeGraphNodeType,
    val label: String,
    val sessionId: MobileSessionId,
    val evidenceRefs: List<LocalEvidenceRef>,
    val updatedAt: OffsetDateTime,
) {
    init {
        require(label.isNotBlank()) { "knowledge_graph_node_label_required" }
        require(evidenceRefs.isNotEmpty()) { "knowledge_graph_node_evidence_required" }
    }
}

public data class KnowledgeGraphEdge(
    val id: KnowledgeGraphEdgeId,
    val from: KnowledgeGraphNodeId,
    val to: KnowledgeGraphNodeId,
    val relationship: KnowledgeRelationship,
    val evidenceRefs: List<LocalEvidenceRef>,
    val confidence: Double,
    val updatedAt: OffsetDateTime,
) {
    init {
        require(evidenceRefs.isNotEmpty()) { "knowledge_graph_edge_evidence_required" }
        require(confidence in 0.0..1.0) { "knowledge_graph_edge_confidence_out_of_range" }
    }
}

public data class KnowledgeGraphSnapshot(
    val nodes: List<KnowledgeGraphNode>,
    val edges: List<KnowledgeGraphEdge>,
) {
    public companion object {
        public fun empty(): KnowledgeGraphSnapshot = KnowledgeGraphSnapshot(emptyList(), emptyList())
    }
}

public enum class ProfileEvidenceStatus {
    CANDIDATE_ONLY,
}

/** A profile entry is a revisable evidence index, not a personality label. */
public data class MobileProfileUpdate(
    val topic: String,
    val subjectTag: String,
    val status: ProfileEvidenceStatus,
    val sessionId: MobileSessionId,
    val evidenceRefs: List<LocalEvidenceRef>,
    val updatedAt: OffsetDateTime,
)

public data class KnowledgeGraphProjection(
    val snapshot: KnowledgeGraphSnapshot,
    val profileUpdates: List<MobileProfileUpdate>,
)

public object KnowledgeGraphProjector {
    /**
     * Projects PC analysis into a phone-readable graph. Existing nodes/edges
     * are preserved and every new relationship remains traceable to media.
     */
    public fun project(
        existing: KnowledgeGraphSnapshot,
        result: PcKnowledgeAnalysisResult,
    ): KnowledgeGraphProjection {
        val mediaNode = KnowledgeGraphNode(
            id = KnowledgeGraphNodeId("media:" + result.resultId),
            type = KnowledgeGraphNodeType.MEDIA_EVIDENCE,
            label = "公开媒体证据 " + result.visitId,
            sessionId = result.sessionId,
            evidenceRefs = result.evidenceRefs,
            updatedAt = result.createdAt,
        )
        val newNodes = mutableListOf(mediaNode)
        val newEdges = mutableListOf<KnowledgeGraphEdge>()
        val profileUpdates = mutableListOf<MobileProfileUpdate>()
        result.associations.forEach { association ->
            val normalizedTopic = association.topic.trim()
            val topicNode = KnowledgeGraphNode(
                id = KnowledgeGraphNodeId("topic:" + normalizedTopic.lowercase()),
                type = KnowledgeGraphNodeType.INTEREST_TOPIC,
                label = normalizedTopic,
                sessionId = result.sessionId,
                evidenceRefs = association.evidenceRefs,
                updatedAt = result.createdAt,
            )
            newNodes += topicNode
            newEdges += KnowledgeGraphEdge(
                id = KnowledgeGraphEdgeId("edge:" + result.resultId + ":" + normalizedTopic.lowercase()),
                from = mediaNode.id,
                to = topicNode.id,
                relationship = association.relationship,
                evidenceRefs = association.evidenceRefs,
                confidence = association.confidence,
                updatedAt = result.createdAt,
            )
            profileUpdates += MobileProfileUpdate(
                topic = normalizedTopic,
                subjectTag = association.subjectTag.trim(),
                status = ProfileEvidenceStatus.CANDIDATE_ONLY,
                sessionId = result.sessionId,
                evidenceRefs = association.evidenceRefs,
                updatedAt = result.createdAt,
            )
        }
        return KnowledgeGraphProjection(
            snapshot = KnowledgeGraphSnapshot(
                nodes = (existing.nodes + newNodes).distinctBy { it.id },
                edges = (existing.edges + newEdges).distinctBy { it.id },
            ),
            profileUpdates = profileUpdates,
        )
    }
}

