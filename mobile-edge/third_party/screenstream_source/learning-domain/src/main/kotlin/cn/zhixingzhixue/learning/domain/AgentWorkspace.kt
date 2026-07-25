package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime

/**
 * A local-only conversation workspace for the independent learning agent.
 *
 * It deliberately contains neither learning-stage state nor inferred interest.
 * A remote agent may only append an assistant message after its service run has
 * produced one; this model therefore has no "fake answer" variant.
 */
public enum class AgentMessageAuthor {
    STUDENT,
    ASSISTANT,
    SYSTEM,
}

public data class AgentConversationMessage(
    val id: String,
    val author: AgentMessageAuthor,
    val body: String,
    val createdAt: OffsetDateTime,
    val remoteRunId: String? = null,
) {
    init {
        require(id.isNotBlank()) { "agent_message_id_required" }
        require(body.trim().isNotEmpty()) { "agent_message_body_required" }
        require(body.length <= MAX_BODY_LENGTH) { "agent_message_body_too_long" }
        require(author != AgentMessageAuthor.ASSISTANT || !remoteRunId.isNullOrBlank()) { "agent_assistant_run_required" }
    }

    private companion object {
        private const val MAX_BODY_LENGTH: Int = 12_000
    }
}

/** A read-only snapshot explicitly transferred from Discover into one agent conversation. */
public data class AgentContextReference(
    val id: String,
    val title: String,
    val summary: String,
    val source: CandidateMediaSource,
    val visitId: String,
    val evidenceRefs: List<LocalEvidenceRef>,
) {
    init {
        require(id.isNotBlank()) { "agent_context_id_required" }
        require(title.trim().isNotEmpty() && summary.trim().isNotEmpty()) { "agent_context_text_required" }
        require(visitId.isNotBlank()) { "agent_context_visit_required" }
        require(evidenceRefs.isNotEmpty()) { "agent_context_evidence_required" }
        require(evidenceRefs.distinct().size == evidenceRefs.size) { "agent_context_evidence_duplicate" }
    }
}

/**
 * An attachment selected on-device. LOCAL_QUEUED means exactly that: the URI
 * metadata is retained locally, while no bytes were uploaded or parsed.
 */
public enum class AgentResourceState {
    LOCAL_QUEUED,
    UPLOADING,
    READY_FOR_AGENT,
    FAILED,
}

public data class AgentResourceAttachment(
    val id: String,
    val uri: String,
    val displayName: String,
    val mimeType: String?,
    val addedAt: OffsetDateTime,
    val state: AgentResourceState = AgentResourceState.LOCAL_QUEUED,
    val sha256: String? = null,
    val errorMessage: String? = null,
) {
    init {
        require(id.isNotBlank()) { "agent_resource_id_required" }
        require(uri.isNotBlank()) { "agent_resource_uri_required" }
        require(displayName.trim().isNotEmpty()) { "agent_resource_name_required" }
        require(sha256 == null || sha256.matches(Regex("[a-f0-9]{64}"))) { "agent_resource_sha256_invalid" }
    }
}

/** Explicit, local knowledge-vault reference.  It is distinct from a captured
 * media context because a student-created note can legitimately have no media
 * evidence. */
public data class AgentKnowledgeReference(
    val id: String,
    val title: String,
    val note: String,
    val evidenceRefs: List<LocalEvidenceRef>,
) {
    init {
        require(id.isNotBlank()) { "agent_knowledge_reference_id_required" }
        require(title.trim().isNotEmpty()) { "agent_knowledge_reference_title_required" }
        require(evidenceRefs.distinct().size == evidenceRefs.size) { "agent_knowledge_reference_evidence_duplicate" }
    }
}

public data class AgentWorkspaceSnapshot(
    val messages: List<AgentConversationMessage>,
    val contextReferences: List<AgentContextReference>,
    val resources: List<AgentResourceAttachment>,
    val knowledgeReferences: List<AgentKnowledgeReference> = emptyList(),
) {
    init {
        require(messages.map { it.id }.distinct().size == messages.size) { "agent_message_ids_must_be_unique" }
        require(contextReferences.map { it.id }.distinct().size == contextReferences.size) {
            "agent_context_ids_must_be_unique"
        }
        require(resources.map { it.id }.distinct().size == resources.size) { "agent_resource_ids_must_be_unique" }
        require(knowledgeReferences.map { it.id }.distinct().size == knowledgeReferences.size) { "agent_knowledge_reference_ids_must_be_unique" }
    }

    public companion object {
        public fun empty(): AgentWorkspaceSnapshot = AgentWorkspaceSnapshot(emptyList(), emptyList(), emptyList(), emptyList())
    }
}
