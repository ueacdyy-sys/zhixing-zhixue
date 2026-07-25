package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.AgentWorkspacePort
import cn.zhixingzhixue.learning.domain.AgentContextReference
import cn.zhixingzhixue.learning.domain.AgentConversationMessage
import cn.zhixingzhixue.learning.domain.AgentMessageAuthor
import cn.zhixingzhixue.learning.domain.AgentResourceAttachment
import cn.zhixingzhixue.learning.domain.AgentKnowledgeReference
import cn.zhixingzhixue.learning.domain.AgentResourceState
import cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import java.time.OffsetDateTime
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONArray
import org.json.JSONObject

/**
 * Device-local journal for the independent agent workspace.
 *
 * URI metadata is retained solely so the student can remove or later submit a
 * selected file. It does not copy files, upload bytes, parse documents, search
 * the web, create assistant messages, or generate downloadable artifacts.
 */
public class AndroidAgentWorkspaceStore(context: Context) : AgentWorkspacePort {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val workspace = MutableStateFlow(read())

    override fun observe(): Flow<AgentWorkspaceSnapshot> = workspace

    override suspend fun beginEmptyConversation() {
        save(AgentWorkspaceSnapshot.empty())
    }

    override suspend fun replaceContextReferences(references: List<AgentContextReference>) {
        save(workspace.value.copy(contextReferences = references.distinctBy { it.id }))
    }

    override suspend fun replaceKnowledgeReferences(references: List<AgentKnowledgeReference>) {
        save(workspace.value.copy(knowledgeReferences = references.distinctBy { it.id }))
    }

    override suspend fun appendMessage(message: AgentConversationMessage) {
        val existing = workspace.value.messages.filterNot { it.id == message.id }
        save(workspace.value.copy(messages = (existing + message).sortedBy { it.createdAt }))
    }

    override suspend fun addResources(resources: List<AgentResourceAttachment>) {
        val updated = (workspace.value.resources + resources)
            .distinctBy { it.id }
            .sortedBy { it.addedAt }
        save(workspace.value.copy(resources = updated))
    }

    override suspend fun updateResource(resource: AgentResourceAttachment) {
        val updated = (workspace.value.resources.filterNot { it.id == resource.id } + resource).sortedBy { it.addedAt }
        save(workspace.value.copy(resources = updated))
    }

    override suspend fun removeResource(resourceId: String) {
        save(workspace.value.copy(resources = workspace.value.resources.filterNot { it.id == resourceId }))
    }

    private fun save(value: AgentWorkspaceSnapshot) {
        preferences.edit().putString(WORKSPACE, requireNotNull(encode(value).toString())).apply()
        workspace.value = value
    }

    private fun read(): AgentWorkspaceSnapshot = runCatching {
        decode(JSONObject(requireNotNull(preferences.getString(WORKSPACE, "{}"))))
    }.getOrDefault(AgentWorkspaceSnapshot.empty())

    private fun encode(value: AgentWorkspaceSnapshot): JSONObject = JSONObject()
        .put("messages", JSONArray(value.messages.map { message ->
            JSONObject()
                .put("id", message.id)
                .put("author", message.author.name)
                .put("body", message.body)
                .put("created_at", message.createdAt.toString())
                .put("remote_run_id", message.remoteRunId)
        }))
        .put("contexts", JSONArray(value.contextReferences.map { reference ->
            JSONObject()
                .put("id", reference.id)
                .put("title", reference.title)
                .put("summary", reference.summary)
                .put("source", reference.source.name)
                .put("visit_id", reference.visitId)
                .put("evidence_refs", JSONArray(reference.evidenceRefs.map { it.value }))
        }))
        .put("resources", JSONArray(value.resources.map { resource ->
            JSONObject()
                .put("id", resource.id)
                .put("uri", resource.uri)
                .put("display_name", resource.displayName)
                .put("mime_type", resource.mimeType)
                .put("added_at", resource.addedAt.toString())
                .put("state", resource.state.name)
                .put("sha256", resource.sha256)
                .put("error_message", resource.errorMessage)
        }))
        .put("knowledge_references", JSONArray(value.knowledgeReferences.map { reference ->
            JSONObject().put("id", reference.id).put("title", reference.title).put("note", reference.note)
                .put("evidence_refs", JSONArray(reference.evidenceRefs.map { it.value }))
        }))

    private fun decode(value: JSONObject): AgentWorkspaceSnapshot = AgentWorkspaceSnapshot(
        messages = decodeEach(value.optJSONArray("messages")) { entry ->
            AgentConversationMessage(
                id = entry.getString("id"),
                author = AgentMessageAuthor.valueOf(entry.getString("author")),
                body = entry.getString("body"),
                createdAt = OffsetDateTime.parse(entry.getString("created_at")),
                remoteRunId = entry.optString("remote_run_id").takeIf { it.isNotBlank() },
            )
        },
        contextReferences = decodeEach(value.optJSONArray("contexts")) { entry ->
            AgentContextReference(
                id = entry.getString("id"),
                title = entry.getString("title"),
                summary = entry.getString("summary"),
                source = CandidateMediaSource.valueOf(entry.getString("source")),
                visitId = entry.getString("visit_id"),
                evidenceRefs = decodeReferences(entry.getJSONArray("evidence_refs")),
            )
        },
        resources = decodeEach(value.optJSONArray("resources")) { entry ->
            AgentResourceAttachment(
                id = entry.getString("id"),
                uri = entry.getString("uri"),
                displayName = entry.getString("display_name"),
                mimeType = entry.optString("mime_type").takeIf { it.isNotBlank() },
                addedAt = OffsetDateTime.parse(entry.getString("added_at")),
                state = AgentResourceState.valueOf(entry.optString("state", AgentResourceState.LOCAL_QUEUED.name)),
                sha256 = entry.optString("sha256").takeIf { it.isNotBlank() },
                errorMessage = entry.optString("error_message").takeIf { it.isNotBlank() },
            )
        },
        knowledgeReferences = decodeEach(value.optJSONArray("knowledge_references")) { entry ->
            AgentKnowledgeReference(
                id = entry.getString("id"),
                title = entry.getString("title"),
                note = entry.optString("note"),
                evidenceRefs = decodeReferences(entry.optJSONArray("evidence_refs") ?: JSONArray()),
            )
        },
    )

    private fun decodeReferences(values: JSONArray): List<LocalEvidenceRef> = List(values.length()) { index ->
        LocalEvidenceRef(values.getString(index))
    }

    private fun <T> decodeEach(values: JSONArray?, decoder: (JSONObject) -> T): List<T> = buildList {
        for (index in 0 until (values?.length() ?: 0)) {
            runCatching { decoder(values!!.getJSONObject(index)) }.getOrNull()?.let(::add)
        }
    }

    private companion object {
        private const val PREFERENCES: String = "zhixing_agent_workspace_v1"
        private const val WORKSPACE: String = "workspace"
    }
}
