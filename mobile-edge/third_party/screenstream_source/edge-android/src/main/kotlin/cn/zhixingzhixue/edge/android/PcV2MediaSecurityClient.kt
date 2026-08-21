package cn.zhixingzhixue.edge.android

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Base64

/** Scope and route facts that must be signed into every newly opened media session. */
public data class V2MediaSecurityBinding(
    val learnerId: String,
    val captureSessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val routeLeaseId: String,
    val routeEpoch: Long,
    val captureEpoch: Long = 1L,
) {
    init {
        require(learnerId.isNotBlank() && captureSessionId.isNotBlank() && captureConsentId.isNotBlank()) {
            "v2_media_security_binding_identity_invalid"
        }
        require(routeLeaseId.isNotBlank() && consentGeneration > 0L && routeEpoch > 0L) {
            "v2_media_security_binding_route_invalid"
        }
    }
}

/** Minimal acknowledgement that intentionally contains no plaintext media. */
public data class V2MediaFragmentReceipt(
    val sequence: Long,
    val mediaSha256: String,
)

/**
 * Android-side v2 encrypted-media client.
 *
 * The PC TLS identity is verified through the already paired SPKI pin; the
 * phone then proves possession of its AndroidKeyStore signing key for each
 * ECDH session.  The resulting AES key stays in [V2MediaSecuritySession]
 * memory and is never written to the capture plan or preferences.
 */
public class PcV2MediaSecurityClient(
    private val credentialStore: AndroidV2DeviceCredentialStore,
    private val credentialClient: PcV2DeviceCredentialClient,
) {
    public suspend fun open(binding: V2MediaSecurityBinding): V2MediaSecuritySession = withContext(Dispatchers.IO) {
        val endpoint = credentialStore.endpoint() ?: throw IllegalStateException("v2_device_credential_not_enrolled")
        val accessToken = credentialClient.accessToken()
        val ephemeral = V2MediaSecurityProtocol.newEphemeralKeyPair()
        val request = V2MediaSecurityOpenRequest(
            deviceId = endpoint.deviceId,
            learnerId = binding.learnerId,
            captureSessionId = binding.captureSessionId,
            captureConsentId = binding.captureConsentId,
            consentGeneration = binding.consentGeneration,
            routeLeaseId = binding.routeLeaseId,
            routeEpoch = binding.routeEpoch,
            captureEpoch = binding.captureEpoch,
            clientEphemeralSpkiBase64 = Base64.getEncoder().encodeToString(ephemeral.public.encoded),
        )
        val response = JSONObject(
            post(
                endpoint = endpoint,
                accessToken = accessToken.value,
                path = "/api/v2/media-sessions",
                body = JSONObject()
                    .put("device_id", request.deviceId)
                    .put("learner_id", request.learnerId)
                    .put("capture_session_id", request.captureSessionId)
                    .put("capture_consent_id", request.captureConsentId)
                    .put("consent_generation", request.consentGeneration)
                    .put("route_lease_id", request.routeLeaseId)
                    .put("route_epoch", request.routeEpoch)
                    .put("capture_epoch", request.captureEpoch)
                    .put("client_ephemeral_spki_b64", request.clientEphemeralSpkiBase64)
                    .put("signature_b64", credentialStore.signMediaSecurityOpen(endpoint.deviceId, request))
                    .toString(),
            ),
        )
        val opened = V2MediaSecurityOpenResponse(
            mediaSecuritySessionId = response.getString("media_security_session_id"),
            deviceId = response.getString("device_id"),
            learnerId = response.getString("learner_id"),
            captureSessionId = response.getString("capture_session_id"),
            captureConsentId = response.getString("capture_consent_id"),
            consentGeneration = response.getLong("consent_generation"),
            routeLeaseId = response.getString("route_lease_id"),
            routeEpoch = response.getLong("route_epoch"),
            serverEphemeralSpkiBase64 = response.getString("server_ephemeral_spki_b64"),
            keyDerivationSaltBase64 = response.getString("key_derivation_salt_b64"),
            expiresAtMs = response.getLong("expires_at_ms"),
            cipherSuite = response.getString("cipher_suite"),
            captureEpoch = response.optLong("capture_epoch", 1L),
        )
        require(opened.deviceId == endpoint.deviceId) { "v2_media_security_response_device_mismatch" }
        require(
            opened.learnerId == binding.learnerId &&
                opened.captureSessionId == binding.captureSessionId &&
                opened.captureConsentId == binding.captureConsentId &&
                opened.consentGeneration == binding.consentGeneration &&
                opened.routeLeaseId == binding.routeLeaseId &&
                opened.routeEpoch == binding.routeEpoch &&
                opened.captureEpoch == binding.captureEpoch,
        ) { "v2_media_security_response_scope_mismatch" }
        require(opened.expiresAtMs > System.currentTimeMillis()) { "v2_media_security_session_expired" }
        V2MediaSecurityProtocol.finishSession(ephemeral.private, opened)
    }

    /** Encrypts and sends one already encoded fragment. Failed uploads do not fall back to RTSP. */
    public suspend fun upload(
        session: V2MediaSecuritySession,
        ptsStartUs: Long,
        ptsEndUs: Long,
        encodedBytes: ByteArray,
    ): V2MediaFragmentReceipt = withContext(Dispatchers.IO) {
        require(session.response.expiresAtMs > System.currentTimeMillis()) { "v2_media_security_session_expired" }
        val endpoint = credentialStore.endpoint() ?: throw IllegalStateException("v2_device_credential_not_enrolled")
        val accessToken = credentialClient.accessToken()
        val envelope = session.encryptNextFragment(ptsStartUs, ptsEndUs, encodedBytes)
        val receipt = JSONObject(
            post(
                endpoint = endpoint,
                accessToken = accessToken.value,
                path = "/api/v2/media-sessions/" + session.response.mediaSecuritySessionId + "/fragments",
                body = JSONObject()
                    .put("header", JSONObject()
                        .put("media_security_session_id", envelope.header.mediaSecuritySessionId)
                        .put("learner_id", envelope.header.learnerId)
                        .put("capture_session_id", envelope.header.captureSessionId)
                        .put("capture_consent_id", envelope.header.captureConsentId)
                        .put("consent_generation", envelope.header.consentGeneration)
                        .put("route_lease_id", envelope.header.routeLeaseId)
                        .put("route_epoch", envelope.header.routeEpoch)
                        .put("capture_epoch", envelope.header.captureEpoch)
                        .put("sequence", envelope.header.sequence)
                        .put("pts_start_us", envelope.header.ptsStartUs)
                        .put("pts_end_us", envelope.header.ptsEndUs)
                        .put("media_sha256", envelope.header.mediaSha256),
                    )
                    .put("nonce_b64", envelope.nonceBase64)
                    .put("ciphertext_b64", envelope.ciphertextBase64)
                    // The gateway also fences its durable buffer at the
                    // envelope level.  This duplicates authenticated header
                    // metadata intentionally: a stale outer epoch must be
                    // rejected before it can be attached to a buffer receipt.
                    .put("capture_epoch", envelope.header.captureEpoch)
                    .toString(),
            ),
        )
        val acceptedSequence = receipt.getLong("sequence")
        val acceptedHash = receipt.getString("media_sha256")
        require(acceptedSequence == envelope.header.sequence && acceptedHash == envelope.header.mediaSha256) {
            "v2_media_fragment_receipt_mismatch"
        }
        V2MediaFragmentReceipt(acceptedSequence, acceptedHash)
    }

    private fun post(
        endpoint: V2DeviceCredentialEndpoint,
        accessToken: String,
        path: String,
        body: String,
    ): String {
        // Supplying a fixed length avoids chunked-transfer framing for every
        // media fragment.  On Android's HttpsURLConnection this materially
        // reduces per-fragment latency and lets the platform reuse the pooled
        // TLS connection to the paired gateway.
        val bodyBytes = body.toByteArray(Charsets.UTF_8)
        val link = PcDeliveryLink(
            baseUrl = endpoint.baseUrl,
            deviceId = endpoint.deviceId,
            pairingToken = accessToken,
            spkiSha256 = endpoint.spkiSha256,
            cursor = null,
        )
        val connection = GatewayTlsConnectionFactory.open(link, endpoint.baseUrl + path, "POST", TIMEOUT_MS).apply {
            doOutput = true
            useCaches = false
            setFixedLengthStreamingMode(bodyBytes.size)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Connection", "keep-alive")
            setRequestProperty("Authorization", "Bearer $accessToken")
        }
        try {
            GatewayTlsConnectionFactory.connectAndVerify(connection, endpoint.spkiSha256)
            connection.outputStream.use { it.write(bodyBytes) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(connection.responseCode in 200..299) { "v2_media_security_http_${connection.responseCode}" }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        private const val TIMEOUT_MS: Int = 12_000
    }
}
