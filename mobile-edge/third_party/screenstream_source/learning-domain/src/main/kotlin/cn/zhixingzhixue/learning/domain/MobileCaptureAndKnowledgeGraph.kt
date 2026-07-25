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
    EXPLAINS,
    RELATED_TO,
    PART_OF,
    CONTRASTS_WITH,
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

/**
 * PC-only semantic material for a student-selected learning path. It is
 * evidence-linked content, not an Android-side placeholder or invented copy.
 */
public data class PcLearningContent(
    val contentId: String,
    val conceptTitle: String,
    val conceptBrief: String,
    val background: String,
    val workedExample: String,
    val guidedPractice: String,
    val selfPractice: String,
    val trustedResources: List<TrustedLearningResource>,
    val evidenceRefs: List<LocalEvidenceRef>,
) {
    init {
        require(contentId.isNotBlank()) { "pc_learning_content_id_required" }
        require(conceptTitle.isNotBlank() && conceptBrief.isNotBlank()) { "pc_learning_content_brief_required" }
        require(background.isNotBlank() && workedExample.isNotBlank()) { "pc_learning_content_l2_required" }
        require(guidedPractice.isNotBlank() && selfPractice.isNotBlank()) { "pc_learning_content_practice_required" }
        require(trustedResources.isNotEmpty()) { "pc_learning_content_resource_required" }
        require(evidenceRefs.isNotEmpty()) { "pc_learning_content_evidence_required" }
    }
}

public data class TrustedLearningResource(
    val title: String,
    val publisher: String,
    val url: String,
) {
    init {
        require(title.isNotBlank() && publisher.isNotBlank()) { "trusted_resource_metadata_required" }
        require(url.startsWith("https://")) { "trusted_resource_https_required" }
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
    /** Present only when the PC has actually prepared the full voluntary path. */
    val learningContent: PcLearningContent? = null,
    val source: CandidateMediaSource = CandidateMediaSource.PHONE_SCREEN,
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
        learningContent?.let { content ->
            require(content.evidenceRefs.all { it in evidenceRefs }) { "pc_learning_content_evidence_not_in_result" }
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

/** Distinguishes a PC proposal from a note deliberately created by the student. */
public enum class KnowledgeGraphNodeOrigin {
    PC_ANALYSIS_SUGGESTION,
    STUDENT_CREATED,
}

/** PC proposals remain visible as drafts until the student accepts them. */
public enum class KnowledgeGraphReviewStatus {
    PENDING_STUDENT,
    CONFIRMED,
}

public data class KnowledgeGraphNode(
    val id: KnowledgeGraphNodeId,
    val type: KnowledgeGraphNodeType,
    val label: String,
    val sessionId: MobileSessionId,
    val evidenceRefs: List<LocalEvidenceRef>,
    val updatedAt: OffsetDateTime,
    val origin: KnowledgeGraphNodeOrigin = KnowledgeGraphNodeOrigin.PC_ANALYSIS_SUGGESTION,
    val reviewStatus: KnowledgeGraphReviewStatus = KnowledgeGraphReviewStatus.PENDING_STUDENT,
    val note: String = "",
) {
    init {
        require(label.isNotBlank()) { "knowledge_graph_node_label_required" }
        require(origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED || evidenceRefs.isNotEmpty()) {
            "pc_knowledge_graph_node_evidence_required"
        }
        require(note.length <= MAX_NOTE_LENGTH) { "knowledge_graph_node_note_too_long" }
    }

    private companion object {
        private const val MAX_NOTE_LENGTH: Int = 12_000
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
    val origin: KnowledgeGraphNodeOrigin = KnowledgeGraphNodeOrigin.PC_ANALYSIS_SUGGESTION,
    val reviewStatus: KnowledgeGraphReviewStatus = KnowledgeGraphReviewStatus.PENDING_STUDENT,
) {
    init {
        require(from != to) { "knowledge_graph_edge_self_reference_forbidden" }
        require(origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED || evidenceRefs.isNotEmpty()) {
            "pc_knowledge_graph_edge_evidence_required"
        }
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

/** Input from the local note editor. It deliberately carries no fabricated media evidence. */
public data class StudentKnowledgeNodeDraft(
    val id: KnowledgeGraphNodeId,
    val label: String,
    val sessionId: MobileSessionId,
    val parentEvidenceRefs: List<LocalEvidenceRef> = emptyList(),
    val note: String = "",
)

/** A student-created relation is explicit, revisable and does not inherit PC confidence. */
public data class StudentKnowledgeEdgeDraft(
    val id: KnowledgeGraphEdgeId,
    val from: KnowledgeGraphNodeId,
    val to: KnowledgeGraphNodeId,
    val relationship: KnowledgeRelationship,
)

public object KnowledgeGraphEditor {
    public fun createStudentNode(
        existing: KnowledgeGraphSnapshot,
        draft: StudentKnowledgeNodeDraft,
        now: OffsetDateTime,
    ): KnowledgeGraphSnapshot {
        require(existing.nodes.none { it.id == draft.id }) { "knowledge_graph_node_id_exists" }
        val node = KnowledgeGraphNode(
            id = draft.id,
            type = KnowledgeGraphNodeType.SUBJECT_KNOWLEDGE,
            label = draft.label.trim(),
            sessionId = draft.sessionId,
            evidenceRefs = draft.parentEvidenceRefs.distinct(),
            updatedAt = now,
            origin = KnowledgeGraphNodeOrigin.STUDENT_CREATED,
            reviewStatus = KnowledgeGraphReviewStatus.CONFIRMED,
            note = draft.note.trim(),
        )
        return existing.copy(nodes = existing.nodes + node)
    }

    public fun updateStudentNode(
        existing: KnowledgeGraphSnapshot,
        nodeId: KnowledgeGraphNodeId,
        label: String,
        note: String,
        now: OffsetDateTime,
    ): KnowledgeGraphSnapshot {
        val target = existing.nodes.firstOrNull { it.id == nodeId } ?: return existing
        require(target.origin == KnowledgeGraphNodeOrigin.STUDENT_CREATED) { "only_student_nodes_are_directly_editable" }
        return existing.copy(nodes = existing.nodes.map { node ->
            if (node.id == nodeId) node.copy(label = label.trim(), note = note.trim(), updatedAt = now) else node
        })
    }

    public fun confirmSuggestion(
        existing: KnowledgeGraphSnapshot,
        nodeId: KnowledgeGraphNodeId,
        now: OffsetDateTime,
    ): KnowledgeGraphSnapshot = existing.copy(nodes = existing.nodes.map { node ->
        if (node.id == nodeId && node.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT) {
            node.copy(reviewStatus = KnowledgeGraphReviewStatus.CONFIRMED, updatedAt = now)
        } else node
    })

    public fun removeNode(existing: KnowledgeGraphSnapshot, nodeId: KnowledgeGraphNodeId): KnowledgeGraphSnapshot =
        existing.copy(
            nodes = existing.nodes.filterNot { it.id == nodeId },
            edges = existing.edges.filterNot { it.from == nodeId || it.to == nodeId },
        )

    public fun createStudentEdge(
        existing: KnowledgeGraphSnapshot,
        draft: StudentKnowledgeEdgeDraft,
        now: OffsetDateTime,
    ): KnowledgeGraphSnapshot {
        require(existing.edges.none { it.id == draft.id }) { "knowledge_graph_edge_id_exists" }
        require(existing.nodes.any { it.id == draft.from } && existing.nodes.any { it.id == draft.to }) {
            "knowledge_graph_edge_node_missing"
        }
        val edge = KnowledgeGraphEdge(
            id = draft.id,
            from = draft.from,
            to = draft.to,
            relationship = draft.relationship,
            evidenceRefs = emptyList(),
            confidence = 1.0,
            updatedAt = now,
            origin = KnowledgeGraphNodeOrigin.STUDENT_CREATED,
            reviewStatus = KnowledgeGraphReviewStatus.CONFIRMED,
        )
        return existing.copy(edges = existing.edges + edge)
    }

    public fun removeEdge(existing: KnowledgeGraphSnapshot, edgeId: KnowledgeGraphEdgeId): KnowledgeGraphSnapshot =
        existing.copy(edges = existing.edges.filterNot { it.id == edgeId })
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
            label = when (result.source) {
                CandidateMediaSource.PHONE_SCREEN -> "手机屏幕证据 " + result.visitId
                CandidateMediaSource.GLASSES_FIRST_PERSON -> "眼镜第一视角证据 " + result.visitId
            },
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
