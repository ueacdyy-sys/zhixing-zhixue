package cn.zhixingzhixue.edge.android

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * Synchronizes only the durable knowledge-event journal.  Candidate-card
 * delivery remains a separate short-lived outbox because knowledge edits must
 * survive long offline periods and PC restarts.
 */
public class PcKnowledgeGraphSyncClient(
    private val linkStore: AndroidPcDeliveryLinkStore,
    private val events: AndroidKnowledgeGraphEventStore,
) {
    public suspend fun synchronizeOnce(): Int = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: return@withContext 0
        var changes = uploadPending(link)
        changes += pullRemote(link)
        changes
    }

    private fun uploadPending(link: PcDeliveryLink): Int {
        val pending = events.pending()
        if (pending.isEmpty()) return 0
        val response = JSONObject(request(
            link,
            "/api/knowledge-graph/events",
            "POST",
            JSONObject().put("events", JSONArray(pending)).toString(),
        ))
        val results = response.getJSONArray("results")
        var accepted = 0
        for (index in 0 until results.length()) {
            val result = results.getJSONObject(index)
            events.markUploadResult(result)
            if (result.optString("state") in setOf("ACKED", "DUPLICATE")) accepted += 1
        }
        return accepted
    }

    private suspend fun pullRemote(link: PcDeliveryLink): Int {
        val response = JSONObject(request(
            link,
            "/api/knowledge-graph/sync?after=${events.cursor()}&limit=200",
            "GET",
            null,
        ))
        val remote = response.getJSONArray("events")
        var applied = 0
        for (index in 0 until remote.length()) {
            val event = remote.getJSONObject(index)
            if (!events.isKnown(event.getString("event_id"))) {
                applyRemoteEvent(event)
                applied += 1
            }
            // Cursor advances only once the event was locally applied or is an
            // idempotent echo of a locally persisted event.
            events.markRemoteApplied(event)
        }
        return applied
    }

    private suspend fun applyRemoteEvent(event: JSONObject) {
        if (event.getString("actor") != "PC_AI") return
        val payload = event.getJSONObject("payload")
        // Historical graph events can contain an embedded v1 analysis result.
        // They remain journal data only: applying them to the old inbox would
        // bypass v2's consent, route, evidence and package transaction.
        if (payload.optJSONObject("analysis_result") != null) return
        // v2 graph-revision ingestion is intentionally unavailable until it
        // shares the same learner-scoped Room transaction as its package.
        if (payload.optString("schema_version") == "CONTENT_GRAPH_REVISION.v2") return
    }

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
            require(connection.responseCode in 200..299) { "pc_graph_sync_http_${connection.responseCode}:${response.take(180)}" }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        private const val TIMEOUT_MS: Int = 12_000
    }
}
