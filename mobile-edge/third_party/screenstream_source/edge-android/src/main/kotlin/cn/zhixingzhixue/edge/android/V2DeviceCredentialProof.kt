package cn.zhixingzhixue.edge.android

import java.security.MessageDigest

/**
 * Canonical bytes for a proof-of-possession request made by the Android
 * Keystore credential.  Keep this representation byte-for-byte aligned with
 * the paired-PC gateway: a signature for token refresh must not be reusable
 * as an authority for another v2 endpoint.
 */
public object V2DeviceCredentialProof {
    public fun payload(
        method: String,
        path: String,
        deviceId: String,
        timestampMs: Long,
        nonce: String,
        bodySha256: String?,
    ): ByteArray {
        require(method == method.uppercase() && method.isNotBlank()) { "v2_device_proof_method_invalid" }
        require(path.startsWith("/api/v2/")) { "v2_device_proof_path_invalid" }
        require(deviceId.isNotBlank() && '\n' !in deviceId && '\r' !in deviceId) { "v2_device_proof_device_id_invalid" }
        require(timestampMs >= 0L) { "v2_device_proof_timestamp_invalid" }
        require(nonce.length in 16..256 && '\n' !in nonce && '\r' !in nonce) { "v2_device_proof_nonce_invalid" }
        val digest = bodySha256 ?: EMPTY_BODY_SHA256
        require(digest.length == SHA256_HEX_LENGTH) { "v2_device_proof_body_hash_invalid" }
        return (
            "ZHIXING_DEVICE_PROOF.v2\n" +
                "$method\n$path\n$deviceId\n$timestampMs\n$nonce\n$digest\n"
            ).toByteArray(Charsets.UTF_8)
    }

    public fun sha256Hex(value: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { byte -> "%02x".format(byte) }

    private const val SHA256_HEX_LENGTH: Int = 64
    private val EMPTY_BODY_SHA256: String = sha256Hex(byteArrayOf())
}
