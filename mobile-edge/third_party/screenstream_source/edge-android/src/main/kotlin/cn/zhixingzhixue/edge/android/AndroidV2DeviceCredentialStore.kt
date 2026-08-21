package cn.zhixingzhixue.edge.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/** Non-secret endpoint metadata needed to renew a v2 short token after restart. */
public data class V2DeviceCredentialEndpoint(
    val baseUrl: String,
    val deviceId: String,
    val spkiSha256: String,
) {
    init {
        require(baseUrl.startsWith("https://")) { "v2_device_endpoint_https_required" }
        require(deviceId.isNotBlank()) { "v2_device_endpoint_device_id_required" }
        GatewayTlsConnectionFactory.validatePin(spkiSha256)
    }
}

/**
 * Non-exportable device credential for the v2 paired-PC control and media
 * path.  The public half is enrolled once; the private half never enters
 * SharedPreferences, JSON, logs, or an HTTP request body.
 *
 * This store intentionally does not persist access tokens.  A process restart
 * renews a short token through a fresh proof-of-possession instead of turning
 * an old bearer into a durable device credential.
 */
public class AndroidV2DeviceCredentialStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    public fun publicKeySpkiBase64(deviceId: String): String = Base64.encodeToString(
        ensureKeyPair(deviceId).public.encoded,
        Base64.NO_WRAP,
    )

    public fun signRefreshProof(
        deviceId: String,
        timestampMs: Long,
        nonce: String,
    ): String {
        val payload = V2DeviceCredentialProof.payload(
            method = "POST",
            path = "/api/v2/device-credentials/refresh",
            deviceId = deviceId,
            timestampMs = timestampMs,
            nonce = nonce,
            bodySha256 = null,
        )
        return signPayload(deviceId, payload)
    }

    /** Signs only the fixed v2 media-session handshake contract with the enrolled Android key. */
    public fun signMediaSecurityOpen(deviceId: String, request: V2MediaSecurityOpenRequest): String {
        require(request.deviceId == deviceId) { "v2_media_security_device_mismatch" }
        return signPayload(deviceId, V2MediaSecurityProtocol.openPayload(request))
    }

    /** Erases the only local private credential after an explicit unpair/revoke. */
    public fun clear(deviceId: String) {
        keyStore().deleteEntry(aliasFor(deviceId))
        preferences.edit()
            .remove(KEY_LAST_DEVICE_ID)
            .remove(KEY_BASE_URL)
            .remove(KEY_SPKI_SHA256)
            .apply()
    }

    public fun lastCredentialDeviceId(): String? =
        preferences.getString(KEY_LAST_DEVICE_ID, null)?.takeIf { it.isNotBlank() }

    public fun saveEndpoint(endpoint: V2DeviceCredentialEndpoint) {
        preferences.edit()
            .putString(KEY_BASE_URL, endpoint.baseUrl.removeSuffix("/"))
            .putString(KEY_LAST_DEVICE_ID, endpoint.deviceId)
            .putString(KEY_SPKI_SHA256, endpoint.spkiSha256)
            .apply()
    }

    public fun endpoint(): V2DeviceCredentialEndpoint? = runCatching {
        V2DeviceCredentialEndpoint(
            baseUrl = preferences.getString(KEY_BASE_URL, null) ?: return null,
            deviceId = preferences.getString(KEY_LAST_DEVICE_ID, null) ?: return null,
            spkiSha256 = preferences.getString(KEY_SPKI_SHA256, null) ?: return null,
        )
    }.getOrNull()

    private fun ensureKeyPair(deviceId: String): java.security.KeyPair {
        require(deviceId.isNotBlank()) { "v2_device_id_required" }
        val alias = aliasFor(deviceId)
        val store = keyStore()
        if (store.containsAlias(alias)) {
            val publicKey = store.getCertificate(alias)?.publicKey
                ?: throw IllegalStateException("v2_device_public_key_missing")
            val privateKey = store.getKey(alias, null) as? PrivateKey
                ?: throw IllegalStateException("v2_device_private_key_missing")
            return java.security.KeyPair(publicKey, privateKey)
        }
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, KEYSTORE).apply {
            initialize(
                KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setUserAuthenticationRequired(false)
                    .build(),
            )
        }
        return generator.generateKeyPair().also {
            preferences.edit().putString(KEY_LAST_DEVICE_ID, deviceId).apply()
        }
    }

    private fun aliasFor(deviceId: String): String =
        "$KEY_ALIAS_PREFIX:${V2DeviceCredentialProof.sha256Hex(deviceId.toByteArray(Charsets.UTF_8))}"

    private fun signPayload(deviceId: String, payload: ByteArray): String {
        val privateKey = keyStore().getKey(aliasFor(deviceId), null) as? PrivateKey
            ?: throw IllegalStateException("v2_device_private_key_missing")
        val signature = Signature.getInstance("SHA256withECDSA").apply {
            initSign(privateKey)
            update(payload)
        }.sign()
        return Base64.encodeToString(signature, Base64.NO_WRAP)
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }

    private companion object {
        private const val KEYSTORE: String = "AndroidKeyStore"
        private const val PREFERENCES: String = "zhixing_v2_device_credential"
        private const val KEY_LAST_DEVICE_ID: String = "last_device_id"
        private const val KEY_BASE_URL: String = "base_url"
        private const val KEY_SPKI_SHA256: String = "spki_sha256"
        private const val KEY_ALIAS_PREFIX: String = "zhixing-v2-device"
    }
}
