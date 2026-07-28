package cn.zhixingzhixue.edge.android

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

/** Explicit student-controlled local-LAN pairing configuration. */
public data class PcDeliveryLink(
    val baseUrl: String,
    val deviceId: String,
    val pairingToken: String,
    val spkiSha256: String,
    val cursor: String?,
) {
    init {
        require(baseUrl.startsWith("https://")) { "pc_delivery_https_required" }
        require(deviceId.isNotBlank()) { "pc_delivery_device_id_required" }
        require(pairingToken.isNotBlank()) { "pc_delivery_pairing_token_required" }
        GatewayTlsConnectionFactory.validatePin(spkiSha256)
    }
}

/** Authoritative state reported by the paired PC capture supervisor. */
public data class PcCaptureSession(
    val sessionId: String,
    val state: String,
    val error: String?,
)

public class AndroidPcDeliveryLinkStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    public fun read(): PcDeliveryLink? = runCatching {
        val url = preferences.getString(BASE_URL, null) ?: return null
        val deviceId = preferences.getString(DEVICE_ID, null) ?: return null
        val token = preferences.getString(TOKEN, null) ?: return null
        val spkiSha256 = preferences.getString(SPKI_SHA256, null) ?: return null
        PcDeliveryLink(url, deviceId, token, spkiSha256, preferences.getString(CURSOR, null))
    }.getOrNull()

    public fun save(link: PcDeliveryLink) {
        preferences.edit()
            .putString(BASE_URL, link.baseUrl.removeSuffix("/"))
            .putString(DEVICE_ID, link.deviceId)
            .putString(TOKEN, link.pairingToken)
            .putString(SPKI_SHA256, link.spkiSha256)
            .putString(CURSOR, link.cursor)
            .apply()
    }

    public fun updateCursor(cursor: String) {
        preferences.edit().putString(CURSOR, cursor).apply()
    }

    public fun localDeviceId(): String {
        preferences.getString(DEVICE_ID, null)?.takeIf { it.isNotBlank() }?.let { return it }
        return ("android-" + UUID.randomUUID()).also { deviceId ->
            preferences.edit().putString(DEVICE_ID, deviceId).apply()
        }
    }

    public fun clear() {
        preferences.edit().clear().apply()
    }

    private companion object {
        private const val PREFERENCES: String = "zhixing_pc_delivery_link"
        private const val BASE_URL: String = "base_url"
        private const val DEVICE_ID: String = "device_id"
        private const val TOKEN: String = "pairing_token"
        private const val SPKI_SHA256: String = "spki_sha256"
        private const val CURSOR: String = "cursor"
    }
}

/**
 * Pulls only from an explicitly paired PC endpoint. It does not discover LAN
 * hosts, expose an Android listener or reuse the ADB debug broadcast.
 */
public class PcDeliveryClient(
    private val linkStore: AndroidPcDeliveryLinkStore,
    private val inbox: AndroidPcResultInbox,
    private val candidateInbox: PcCandidateCardInbox,
    private val knowledgeGraphSync: PcKnowledgeGraphSyncClient,
) {
    public suspend fun pair(baseUrl: String, pairingToken: String): PcDeliveryLink = withContext(Dispatchers.IO) {
        // Parsing (including HTTPS and pin validation) happens before opening a socket.
        val endpoint = GatewayTlsConnectionFactory.parsePairingAddress(baseUrl)
        val deviceId = linkStore.localDeviceId()
        val response = anonymousRequest(
            endpoint,
            endpoint.baseUrl + "/api/mobile-outbox/devices/pair",
            JSONObject()
                .put("device_id", deviceId)
                .put("pairing_token", pairingToken.trim())
                .toString(),
        )
        val document = JSONObject(response)
        val link = PcDeliveryLink(
            baseUrl = endpoint.baseUrl,
            deviceId = document.getString("device_id"),
            pairingToken = document.getString("access_token"),
            spkiSha256 = endpoint.spkiSha256,
            cursor = document.optString("cursor").takeIf { it.isNotBlank() },
        )
        linkStore.save(link)
        link
    }

    /** First-use LAN flow: a discovered record still goes through TLS pinning and pairing. */
    public suspend fun pairDiscovered(candidate: LanGatewayCandidate): PcDeliveryLink =
        pair(candidate.pairingAddress, candidate.pairingToken)

    /**
     * DHCP may change a PC's address.  Re-discovery may update only the origin
     * of an existing trusted link when the advertised SPKI remains identical;
     * it never performs a silent first pairing or accepts a new certificate.
     */
    public suspend fun reconnectFromNearbyGateway(): Boolean = withContext(Dispatchers.IO) {
        val current = linkStore.read() ?: return@withContext false
        val match = LanGatewayDiscovery().discover().firstOrNull { candidate ->
            MessageDigest.isEqual(candidate.spkiSha256.toByteArray(Charsets.US_ASCII), current.spkiSha256.toByteArray(Charsets.US_ASCII))
        } ?: return@withContext false
        val endpoint = GatewayTlsConnectionFactory.parsePairingAddress(match.pairingAddress)
        if (endpoint.baseUrl == current.baseUrl) return@withContext false
        linkStore.save(current.copy(baseUrl = endpoint.baseUrl, spkiSha256 = endpoint.spkiSha256))
        true
    }

    /**
     * Registers the stream only after the Android RTSP facade reports STREAMING.
     * The PC derives the RTSP host from this authenticated TLS connection; the
     * phone therefore never submits an arbitrary network URL.
     */
    public suspend fun startCaptureSession(sessionId: String, rtspPort: Int, rtspPath: String): PcCaptureSession = withContext(Dispatchers.IO) {
        require(sessionId.isNotBlank()) { "capture_session_id_required" }
        require(rtspPort in 1..65535) { "capture_rtsp_port_invalid" }
        require(rtspPath.matches(Regex("[A-Za-z0-9._~-]+"))) { "capture_rtsp_path_invalid" }
        val link = linkStore.read() ?: throw IllegalStateException("pc_delivery_not_paired")
        parseCaptureSession(request(
            link.baseUrl + "/api/capture-sessions",
            "POST",
            link,
            JSONObject()
                .put("session_id", sessionId)
                .put("rtsp_port", rtspPort)
                .put("rtsp_path", rtspPath)
                .put("source", "PHONE_SCREEN")
                .toString(),
        ))
    }

    public suspend fun stopCaptureSession(sessionId: String): PcCaptureSession = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: throw IllegalStateException("pc_delivery_not_paired")
        parseCaptureSession(request(link.baseUrl + "/api/capture-sessions/" + java.net.URLEncoder.encode(sessionId, Charsets.UTF_8.name()) + "/stop", "POST", link, "{}"))
    }

    /**
     * Reads the authoritative PC supervisor state for an active phone capture.
     *
     * Starting a session only proves that the PC accepted the first request.
     * The V5 connection surface must subsequently render this state instead of
     * retaining a stale local "analysing" label if the PC worker later fails.
     */
    public suspend fun captureSessionStatus(sessionId: String): PcCaptureSession = withContext(Dispatchers.IO) {
        require(sessionId.isNotBlank()) { "capture_session_id_required" }
        val link = linkStore.read() ?: throw IllegalStateException("pc_delivery_not_paired")
        val encodedSessionId = java.net.URLEncoder.encode(sessionId, Charsets.UTF_8.name())
        parseCaptureSession(request(link.baseUrl + "/api/capture-sessions/" + encodedSessionId, "GET", link, null))
    }

    public suspend fun synchronizeOnce(): Int = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: return@withContext 0
        val endpoint = link.baseUrl + "/api/mobile-outbox/messages?device_id=" +
            java.net.URLEncoder.encode(link.deviceId, Charsets.UTF_8.name()) + "&limit=20"
        val response = request(endpoint, "GET", link, null)
        val deliveries = JSONObject(response).getJSONArray("messages")
        var accepted = 0
        for (index in 0 until deliveries.length()) {
            val delivery = deliveries.getJSONObject(index)
            val deliveryId = delivery.getString("message_id")
            val deliveryToken = delivery.getString("delivery_token")
            val payload = delivery.getJSONObject("payload")
            val acceptedByLocalStore = try {
                require(payload.getString("schema_version") == "mobile_result_message.v1") {
                    "mobile_result_message_schema_unsupported"
                }
                when (payload.getString("message_type")) {
                    "ANALYSIS_RESULT" -> {
                        inbox.accept(payload.getJSONObject("analysis_result").toString())
                        true
                    }
                    "CANDIDATE_CARD" -> candidateInbox.accept(payload)
                    else -> throw IllegalArgumentException("mobile_result_message_type_unsupported")
                }
            } catch (error: IllegalArgumentException) {
                nack(link, deliveryId, deliveryToken, error.message ?: "rejected_schema_or_gate", retryable = false)
                continue
            } catch (error: org.json.JSONException) {
                nack(link, deliveryId, deliveryToken, "rejected_json", retryable = false)
                continue
            } catch (error: Exception) {
                nack(link, deliveryId, deliveryToken, "local_persist_retryable", retryable = true)
                continue
            }
            if (!acceptedByLocalStore) {
                nack(link, deliveryId, deliveryToken, "rejected_schema_or_gate", retryable = false)
                continue
            }
            // The local repository transaction has completed. ACK is deliberately last.
            request(
                link.baseUrl + "/api/mobile-outbox/messages/ack",
                "POST",
                link,
                JSONObject()
                    .put("device_id", link.deviceId)
                    .put("message_id", deliveryId)
                    .put("delivery_token", deliveryToken)
                    .toString(),
            )
            linkStore.updateCursor(deliveryId)
            accepted += 1
        }
        // A graph event is long-lived knowledge state, not a time-limited
        // notification.  Synchronize it after durable PC-result delivery.
        accepted + knowledgeGraphSync.synchronizeOnce()
    }

    private fun nack(
        link: PcDeliveryLink,
        messageId: String,
        deliveryToken: String,
        reason: String,
        retryable: Boolean,
    ) {
        request(
            link.baseUrl + "/api/mobile-outbox/messages/nack",
            "POST",
            link,
            JSONObject()
                .put("device_id", link.deviceId)
                .put("message_id", messageId)
                .put("delivery_token", deliveryToken)
                .put("reason", reason.take(240))
                .put("retryable", retryable)
                .toString(),
        )
    }

    private fun parseCaptureSession(raw: String): PcCaptureSession {
        val document = JSONObject(raw)
        return PcCaptureSession(
            sessionId = document.getString("session_id"),
            state = document.getString("state"),
            error = document.optString("error").takeIf { it.isNotBlank() },
        )
    }

    /** Revokes the bearer token at the PC boundary before local state is removed. */
    public suspend fun unpair(): Unit = withContext(Dispatchers.IO) {
        val link = linkStore.read() ?: return@withContext
        runCatching { request(link.baseUrl + "/api/mobile-outbox/devices/me", "DELETE", link, null) }
        linkStore.clear()
    }

    private fun request(url: String, method: String, link: PcDeliveryLink, body: String?): String {
        val connection = GatewayTlsConnectionFactory.open(link, url, method, TIMEOUT_MS).apply {
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer " + link.pairingToken)
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, link.spkiSha256)
            if (body != null) {
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(connection.responseCode in 200..299) { "pc_delivery_http_" + connection.responseCode }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun anonymousRequest(endpoint: GatewayTlsConnectionFactory.PairingEndpoint, url: String, body: String): String {
        val provisionalLink = PcDeliveryLink(endpoint.baseUrl, "pairing-bootstrap", "pairing-bootstrap", endpoint.spkiSha256, null)
        val connection = GatewayTlsConnectionFactory.open(provisionalLink, url, "POST", TIMEOUT_MS).apply {
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, endpoint.spkiSha256)
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(connection.responseCode in 200..299) { "pc_pairing_http_" + connection.responseCode }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        private const val TIMEOUT_MS: Int = 12_000
    }
}
