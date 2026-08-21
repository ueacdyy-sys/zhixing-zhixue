package cn.zhixingzhixue.edge.android

import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.UUID

/** A short bearer obtained only by proof of possession of the Android Keystore key. */
public data class V2DeviceAccessToken(
    val value: String,
    val expiresAtElapsedRealtimeMs: Long,
    val credentialGeneration: Long,
) {
    init {
        require(value.isNotBlank()) { "v2_device_access_token_required" }
        require(expiresAtElapsedRealtimeMs > 0L) { "v2_device_access_token_expiry_invalid" }
        require(credentialGeneration > 0L) { "v2_device_credential_generation_invalid" }
    }
}

/**
 * V2 bootstrap and renewal client.  This is intentionally separate from the
 * frozen legacy [PcDeliveryClient]: callers must opt into a v2 endpoint and
 * cannot silently downgrade a failed v2 renewal to the year-long bearer.
 */
public class PcV2DeviceCredentialClient(
    private val credentialStore: AndroidV2DeviceCredentialStore,
) {
    @Volatile private var inMemoryToken: V2DeviceAccessToken? = null

    public suspend fun enroll(
        link: PcDeliveryLink,
        pairingToken: String,
    ): V2DeviceAccessToken = withContext(Dispatchers.IO) {
        val endpoint = GatewayTlsConnectionFactory.endpointFromTrustedLink(link)
        val document = JSONObject(
            anonymousPost(
                endpoint = endpoint,
                path = "/api/v2/device-credentials/enroll",
                body = JSONObject()
                    .put("device_id", link.deviceId)
                    .put("pairing_token", pairingToken.trim())
                    .put("public_key_spki_b64", credentialStore.publicKeySpkiBase64(link.deviceId))
                    .toString(),
            ),
        )
        credentialStore.saveEndpoint(
            V2DeviceCredentialEndpoint(endpoint.baseUrl, document.getString("device_id"), endpoint.spkiSha256),
        )
        tokenFrom(document)
    }

    /**
     * Gets a token without retaining it in persistent storage.  After process
     * death, [credentialStore] supplies the public endpoint and Keystore key
     * needed for a new signed renewal.
     */
    public suspend fun accessToken(): V2DeviceAccessToken = withContext(Dispatchers.IO) {
        val now = SystemClock.elapsedRealtime()
        inMemoryToken?.takeIf { it.expiresAtElapsedRealtimeMs - now > RENEW_EARLY_MS }?.let { return@withContext it }
        val endpoint = credentialStore.endpoint() ?: throw IllegalStateException("v2_device_credential_not_enrolled")
        val timestampMs = System.currentTimeMillis()
        val nonce = UUID.randomUUID().toString() + UUID.randomUUID().toString().take(4)
        val signature = credentialStore.signRefreshProof(endpoint.deviceId, timestampMs, nonce)
        val response = authenticatedPost(
            endpoint = endpoint,
            path = "/api/v2/device-credentials/refresh",
            headers = mapOf(
                "X-Zhixing-Device-Id" to endpoint.deviceId,
                "X-Zhixing-Device-Timestamp-Ms" to timestampMs.toString(),
                "X-Zhixing-Device-Nonce" to nonce,
                "X-Zhixing-Device-Signature" to signature,
            ),
        )
        tokenFrom(JSONObject(response))
    }

    /** Drops only the in-memory short token; the Keystore key survives until explicit unpair. */
    public fun forgetInMemoryToken() {
        inMemoryToken = null
    }

    public fun clearAfterRevocation() {
        credentialStore.lastCredentialDeviceId()?.let(credentialStore::clear)
        inMemoryToken = null
    }

    private fun tokenFrom(document: JSONObject): V2DeviceAccessToken {
        val token = V2DeviceAccessToken(
            value = document.getString("access_token"),
            expiresAtElapsedRealtimeMs = SystemClock.elapsedRealtime() + document.getLong("expires_in_seconds") * 1_000L,
            credentialGeneration = document.getLong("credential_generation"),
        )
        inMemoryToken = token
        return token
    }

    private fun anonymousPost(
        endpoint: GatewayTlsConnectionFactory.PairingEndpoint,
        path: String,
        body: String,
    ): String {
        val provisional = PcDeliveryLink(
            endpoint.baseUrl,
            "v2-device-bootstrap",
            "v2-device-bootstrap",
            endpoint.spkiSha256,
            null,
        )
        val connection = GatewayTlsConnectionFactory.open(provisional, endpoint.baseUrl + path, "POST", TIMEOUT_MS).apply {
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, endpoint.spkiSha256)
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            return readResponse(connection, "v2_device_enroll")
        } finally {
            connection.disconnect()
        }
    }

    private fun authenticatedPost(
        endpoint: V2DeviceCredentialEndpoint,
        path: String,
        headers: Map<String, String>,
    ): String {
        val provisional = PcDeliveryLink(
            endpoint.baseUrl,
            endpoint.deviceId,
            "v2-device-refresh",
            endpoint.spkiSha256,
            null,
        )
        val connection = GatewayTlsConnectionFactory.open(provisional, endpoint.baseUrl + path, "POST", TIMEOUT_MS).apply {
            setRequestProperty("Accept", "application/json")
            headers.forEach { (name, value) -> setRequestProperty(name, value) }
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, endpoint.spkiSha256)
            return readResponse(connection, "v2_device_refresh")
        } finally {
            connection.disconnect()
        }
    }

    private fun readResponse(connection: java.net.HttpURLConnection, operation: String): String {
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        require(connection.responseCode in 200..299) { "${operation}_http_${connection.responseCode}" }
        return response
    }

    private companion object {
        private const val TIMEOUT_MS: Int = 12_000
        private const val RENEW_EARLY_MS: Long = 45_000L
    }
}
