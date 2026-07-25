package cn.zhixingzhixue.edge.android

import android.content.Context
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import cn.zhixingzhixue.learning.domain.AgentResourceAttachment
import cn.zhixingzhixue.learning.domain.AgentWorkspaceSnapshot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

public enum class AgentRequestMode { ANSWER, WEB_SEARCH, EXPORT_MARKDOWN, EXPORT_DOCX, EXPORT_PPTX, EXPORT_PDF }

public data class PcAgentArtifact(val runId: String, val displayName: String)

/** Safe status projection: the paired PC never returns third-party API keys to Android. */
public data class PcAgentGatewayStatus(
    val state: String,
    val provider: String?,
    val model: String?,
    val configured: Boolean,
    val connectivity: String,
    val errorCode: String?,
    val errorMessage: String?,
)

public data class PcAgentResourceUpload(
    val state: String,
    val sha256: String?,
    val errorMessage: String?,
)

public data class PcAgentGatewayRun(
    val runId: String,
    val state: String,
    val answer: String?,
    val errorCode: String?,
    val errorMessage: String?,
    val artifact: PcAgentArtifact?,
)

/** Authenticated client for the already paired PC local gateway. */
public class PcAgentGatewayClient(
    private val linkStore: AndroidPcDeliveryLinkStore,
) {
    public suspend fun readStatus(): PcAgentGatewayStatus = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: throw IllegalStateException("pc_agent_not_paired")
        val document = JSONObject(request(link, "/api/agent/status", "GET", null))
        val error = document.optJSONObject("error")
        PcAgentGatewayStatus(
            state = document.getString("state"),
            provider = document.optString("provider").takeIf { it.isNotBlank() },
            model = document.optString("model").takeIf { it.isNotBlank() },
            configured = document.optBoolean("configured", false),
            connectivity = document.optString("connectivity", "UNKNOWN"),
            errorCode = error?.optString("code")?.takeIf { it.isNotBlank() },
            errorMessage = error?.optString("message")?.takeIf { it.isNotBlank() },
        )
    }

    public suspend fun submit(
        mode: AgentRequestMode,
        prompt: String,
        workspace: AgentWorkspaceSnapshot,
    ): PcAgentGatewayRun = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: throw IllegalStateException("pc_agent_not_paired")
        val body = JSONObject()
            .put("client_request_id", UUID.randomUUID().toString())
            .put("conversation_id", "mobile-local-workspace-v1")
            .put("mode", mode.name)
            .put("prompt", prompt)
            .put("contexts", JSONArray(workspace.contextReferences.map { reference ->
                JSONObject()
                    .put("id", reference.id)
                    .put("title", reference.title)
                    .put("summary", reference.summary)
                    .put("source", reference.source.name)
                    .put("visit_id", reference.visitId)
                    .put("evidence_refs", JSONArray(reference.evidenceRefs.map { it.value }))
            }))
            .put("resources", JSONArray(workspace.resources.map(::resourceJson)))
            .put("knowledge_references", JSONArray(workspace.knowledgeReferences.map { reference ->
                JSONObject().put("id", reference.id).put("title", reference.title).put("note", reference.note)
                    .put("evidence_refs", JSONArray(reference.evidenceRefs.map { it.value }))
            }))
            .toString()
        val document = JSONObject(request(link, "/api/agent/runs", "POST", body))
        val error = document.optJSONObject("error")
        val artifact = document.optJSONObject("artifact")?.let {
            PcAgentArtifact(it.getString("run_id"), it.getString("display_name"))
        }
        PcAgentGatewayRun(
            runId = document.getString("run_id"),
            state = document.getString("state"),
            answer = document.optString("answer").takeIf { it.isNotBlank() },
            errorCode = error?.optString("code")?.takeIf { it.isNotBlank() },
            errorMessage = error?.optString("message")?.takeIf { it.isNotBlank() },
            artifact = artifact,
        )
    }

    /** Downloads through the same pinned TLS channel, then commits the verified bytes to Downloads. */
    public suspend fun downloadArtifact(context: Context, artifact: PcAgentArtifact): Uri = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: throw IllegalStateException("pc_agent_not_paired")
        val safeName = artifact.displayName.replace(Regex("[^A-Za-z0-9._-]"), "_").take(120)
        val connection = GatewayTlsConnectionFactory.open(
            link,
            link.baseUrl + "/api/agent/artifacts/" + artifact.runId + "/file",
            "GET",
            TIMEOUT_MS,
        ).apply {
            setRequestProperty("Accept", "text/markdown, application/octet-stream")
            setRequestProperty("Authorization", "Bearer " + link.pairingToken)
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, link.spkiSha256)
            require(connection.responseCode in 200..299) { "pc_artifact_http_${connection.responseCode}" }
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, safeName)
                put(MediaStore.Downloads.MIME_TYPE, connection.contentType ?: "text/markdown")
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
            }
            val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            } else {
                MediaStore.Files.getContentUri("external")
            }
            val uri = context.contentResolver.insert(collection, values)
                ?: throw IllegalStateException("pc_artifact_destination_unavailable")
            try {
                connection.inputStream.use { input ->
                    context.contentResolver.openOutputStream(uri)?.use { output -> input.copyTo(output) }
                        ?: throw IllegalStateException("pc_artifact_destination_unavailable")
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    values.clear()
                    values.put(MediaStore.Downloads.IS_PENDING, 0)
                    context.contentResolver.update(uri, values, null, null)
                }
                uri
            } catch (error: Exception) {
                context.contentResolver.delete(uri, null, null)
                throw error
            }
        } finally {
            connection.disconnect()
        }
    }

    /** Uploads actual SAF bytes to the paired PC and verifies the returned SHA-256 state. */
    public suspend fun uploadResource(context: Context, resource: AgentResourceAttachment): PcAgentResourceUpload = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: throw IllegalStateException("pc_agent_not_paired")
        val bytes = context.contentResolver.openInputStream(Uri.parse(resource.uri))?.use { input ->
            val output = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                if (output.size() + read > MAX_RESOURCE_BYTES) throw IllegalArgumentException("agent_resource_too_large")
                output.write(buffer, 0, read)
            }
            output.toByteArray()
        } ?: throw IllegalArgumentException("agent_resource_open_failed")
        val sha256 = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val connection = GatewayTlsConnectionFactory.open(
            link,
            link.baseUrl + "/api/agent/resources/" + resource.id,
            "PUT",
            TIMEOUT_MS,
        ).apply {
            doOutput = true
            setFixedLengthStreamingMode(bytes.size)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer " + link.pairingToken)
            setRequestProperty("Content-Type", resource.mimeType ?: "application/octet-stream")
            setRequestProperty("X-Resource-Name", resource.displayName)
            setRequestProperty("X-Resource-Sha256", sha256)
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, link.spkiSha256)
            connection.outputStream.use { it.write(bytes) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(connection.responseCode in 200..299) { "pc_resource_http_${connection.responseCode}:${response.take(180)}" }
            val document = JSONObject(response)
            PcAgentResourceUpload(
                state = document.getString("state"),
                sha256 = document.optString("sha256").takeIf { it.isNotBlank() },
                errorMessage = document.optString("error").takeIf { it.isNotBlank() },
            )
        } finally {
            connection.disconnect()
        }
    }

    private fun resourceJson(resource: AgentResourceAttachment): JSONObject = JSONObject()
        .put("id", resource.id)
        .put("display_name", resource.displayName)
        .put("mime_type", resource.mimeType)
        .put("state", resource.state.name)

    private fun request(link: PcDeliveryLink, path: String, method: String, body: String?): String {
        val connection = GatewayTlsConnectionFactory.open(link, link.baseUrl + path, method, TIMEOUT_MS).apply {
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer " + link.pairingToken)
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, link.spkiSha256)
            if (body != null) connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(connection.responseCode in 200..299) { "pc_agent_http_" + connection.responseCode + ":" + response.take(180) }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        private const val TIMEOUT_MS: Int = 65_000
        private const val MAX_RESOURCE_BYTES: Int = 32 * 1024 * 1024
    }
}
