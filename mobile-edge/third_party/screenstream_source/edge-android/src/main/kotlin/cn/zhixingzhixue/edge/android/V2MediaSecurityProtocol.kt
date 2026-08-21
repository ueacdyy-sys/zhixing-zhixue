package cn.zhixingzhixue.edge.android

import java.security.MessageDigest
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** Immutable, scope-bound input to the v2 encrypted-media session handshake. */
public data class V2MediaSecurityOpenRequest(
    val deviceId: String,
    val learnerId: String,
    val captureSessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val routeLeaseId: String,
    val routeEpoch: Long,
    val clientEphemeralSpkiBase64: String,
    val captureEpoch: Long = 1L,
) {
    init {
        val identifiers = listOf(
            deviceId,
            learnerId,
            captureSessionId,
            captureConsentId,
            routeLeaseId,
            clientEphemeralSpkiBase64,
        )
        require(identifiers.all { it.isNotBlank() && '\n' !in it && '\r' !in it }) {
            "v2_media_security_open_identifier_invalid"
        }
        require(consentGeneration > 0L && routeEpoch > 0L && captureEpoch > 0L) { "v2_media_security_open_generation_invalid" }
    }
}

/** Public, non-secret response from the PC after it verifies the device proof. */
public data class V2MediaSecurityOpenResponse(
    val mediaSecuritySessionId: String,
    val deviceId: String,
    val learnerId: String,
    val captureSessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val routeLeaseId: String,
    val routeEpoch: Long,
    val serverEphemeralSpkiBase64: String,
    val keyDerivationSaltBase64: String,
    val expiresAtMs: Long,
    val cipherSuite: String = "P-256-HKDF-SHA256-AES-256-GCM",
    val captureEpoch: Long = 1L,
) {
    init {
        require(mediaSecuritySessionId.isNotBlank() && deviceId.isNotBlank() && learnerId.isNotBlank()) {
            "v2_media_security_session_identity_invalid"
        }
        require(captureSessionId.isNotBlank() && captureConsentId.isNotBlank() && routeLeaseId.isNotBlank()) {
            "v2_media_security_session_binding_invalid"
        }
        require(consentGeneration > 0L && routeEpoch > 0L && captureEpoch > 0L && expiresAtMs > 0L) {
            "v2_media_security_session_generation_invalid"
        }
        require(cipherSuite == "P-256-HKDF-SHA256-AES-256-GCM") { "v2_media_security_cipher_suite_unsupported" }
    }
}

/** Immutable authenticated metadata for exactly one encrypted encoded fragment. */
public data class V2MediaFragmentHeader(
    val mediaSecuritySessionId: String,
    val learnerId: String,
    val captureSessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val routeLeaseId: String,
    val routeEpoch: Long,
    val sequence: Long,
    val ptsStartUs: Long,
    val ptsEndUs: Long,
    val mediaSha256: String,
    val captureEpoch: Long = 1L,
) {
    init {
        val identifiers = listOf(
            mediaSecuritySessionId,
            learnerId,
            captureSessionId,
            captureConsentId,
            routeLeaseId,
        )
        require(identifiers.all { it.isNotBlank() && '\n' !in it && '\r' !in it }) {
            "v2_media_fragment_identifier_invalid"
        }
        require(consentGeneration > 0L && routeEpoch > 0L && captureEpoch > 0L && sequence >= 0L) {
            "v2_media_fragment_sequence_invalid"
        }
        require(ptsStartUs >= 0L && ptsEndUs >= ptsStartUs) { "v2_media_fragment_pts_invalid" }
        require(mediaSha256.isEmpty() || mediaSha256.matches(Regex("[0-9a-f]{64}"))) {
            "v2_media_fragment_hash_invalid"
        }
    }
}

/** Ciphertext envelope sent over the already SPKI-pinned PC HTTPS connection. */
public data class V2MediaEncryptedFragment(
    val header: V2MediaFragmentHeader,
    val nonceBase64: String,
    val ciphertextBase64: String,
)

/** An in-memory media session; neither its derived fragment key nor cursor is persisted. */
public class V2MediaSecuritySession internal constructor(
    public val response: V2MediaSecurityOpenResponse,
    private val fragmentKey: ByteArray,
) {
    private val nextSequence: AtomicLong = AtomicLong(0L)

    public fun encryptNextFragment(ptsStartUs: Long, ptsEndUs: Long, plaintext: ByteArray): V2MediaEncryptedFragment {
        val sequence = nextSequence.getAndIncrement()
        return V2MediaSecurityProtocol.encryptFragment(
            fragmentKey,
            V2MediaFragmentHeader(
                mediaSecuritySessionId = response.mediaSecuritySessionId,
                learnerId = response.learnerId,
                captureSessionId = response.captureSessionId,
                captureConsentId = response.captureConsentId,
                consentGeneration = response.consentGeneration,
                routeLeaseId = response.routeLeaseId,
                routeEpoch = response.routeEpoch,
                captureEpoch = response.captureEpoch,
                sequence = sequence,
                ptsStartUs = ptsStartUs,
                ptsEndUs = ptsEndUs,
                mediaSha256 = "",
            ),
            plaintext,
        )
    }
}

/**
 * Byte-for-byte contract shared with the PC's ``MediaSecurityOpenRequest``.
 *
 * The Android Keystore signs these bytes rather than an implementation-specific
 * JSON serializer output, so a proof cannot be reinterpreted on another v2
 * endpoint or with altered learner/session/route binding.
 */
public object V2MediaSecurityProtocol {
    /** Creates a fresh P-256 ECDH keypair for one short-lived media session. */
    public fun newEphemeralKeyPair(): KeyPair = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"))
    }.generateKeyPair()

    public fun openPayload(request: V2MediaSecurityOpenRequest): ByteArray = (
        "ZHIXING_MEDIA_SECURITY_OPEN.v1\n" +
            "{" +
            "\"capture_consent_id\":${jsonString(request.captureConsentId)}," +
            "\"capture_epoch\":${request.captureEpoch}," +
            "\"capture_session_id\":${jsonString(request.captureSessionId)}," +
            "\"client_ephemeral_spki_b64\":${jsonString(request.clientEphemeralSpkiBase64)}," +
            "\"consent_generation\":${request.consentGeneration}," +
            "\"device_id\":${jsonString(request.deviceId)}," +
            "\"learner_id\":${jsonString(request.learnerId)}," +
            "\"route_epoch\":${request.routeEpoch}," +
            "\"route_lease_id\":${jsonString(request.routeLeaseId)}" +
            "}\n"
        ).toByteArray(Charsets.UTF_8)

    /** HKDF info bytes shared exactly with the PC; salt and ECDH secret remain separate. */
    public fun keyDerivationInfo(response: V2MediaSecurityOpenResponse): ByteArray = (
        "ZHIXING_MEDIA_FRAGMENT_KEY.v1\n" +
            "{" +
            "\"capture_consent_id\":${jsonString(response.captureConsentId)}," +
            "\"capture_epoch\":${response.captureEpoch}," +
            "\"capture_session_id\":${jsonString(response.captureSessionId)}," +
            "\"consent_generation\":${response.consentGeneration}," +
            "\"device_id\":${jsonString(response.deviceId)}," +
            "\"learner_id\":${jsonString(response.learnerId)}," +
            "\"media_security_session_id\":${jsonString(response.mediaSecuritySessionId)}," +
            "\"route_epoch\":${response.routeEpoch}," +
            "\"route_lease_id\":${jsonString(response.routeLeaseId)}" +
            "}\n"
        ).toByteArray(Charsets.UTF_8)

    /** Derives the 32-byte AES-GCM key from a P-256 ephemeral ECDH exchange. */
    public fun deriveFragmentKey(
        localEphemeralPrivateKey: PrivateKey,
        peerEphemeralSpkiBase64: String,
        response: V2MediaSecurityOpenResponse,
    ): ByteArray {
        require(localEphemeralPrivateKey.algorithm.equals("EC", ignoreCase = true)) {
            "v2_media_security_local_key_invalid"
        }
        val peer = try {
            KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(decodeBase64(
                peerEphemeralSpkiBase64,
                "v2_media_security_peer_key_invalid",
            )))
        } catch (error: Exception) {
            throw IllegalArgumentException("v2_media_security_peer_key_invalid", error)
        }
        require(peer.algorithm.equals("EC", ignoreCase = true)) { "v2_media_security_peer_key_invalid" }
        val salt = decodeBase64(response.keyDerivationSaltBase64, "v2_media_security_kdf_salt_invalid")
        require(salt.size == HKDF_SALT_BYTES) { "v2_media_security_kdf_salt_invalid" }
        val sharedSecret = try {
            KeyAgreement.getInstance("ECDH").apply {
                init(localEphemeralPrivateKey)
                doPhase(peer, true)
            }.generateSecret()
        } catch (error: Exception) {
            throw IllegalArgumentException("v2_media_security_ecdh_failed", error)
        }
        return hkdfSha256(sharedSecret, salt, keyDerivationInfo(response))
    }

    /** Finishes the ECDH handshake and retains the resulting AES key only in the returned session. */
    public fun finishSession(
        clientEphemeralPrivateKey: PrivateKey,
        response: V2MediaSecurityOpenResponse,
    ): V2MediaSecuritySession = V2MediaSecuritySession(
        response = response,
        fragmentKey = deriveFragmentKey(
            clientEphemeralPrivateKey,
            response.serverEphemeralSpkiBase64,
            response,
        ),
    )

    /** AES-256-GCM encrypts the encoded bytes and authenticates the complete routing header as AAD. */
    public fun encryptFragment(
        fragmentKey: ByteArray,
        header: V2MediaFragmentHeader,
        plaintext: ByteArray,
    ): V2MediaEncryptedFragment {
        require(fragmentKey.size == FRAGMENT_KEY_BYTES) { "v2_media_fragment_key_invalid" }
        require(plaintext.isNotEmpty()) { "v2_media_fragment_empty" }
        val boundHeader = header.copy(mediaSha256 = sha256Hex(plaintext))
        val nonce = ByteArray(GCM_NONCE_BYTES).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance(AES_GCM_TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, javax.crypto.spec.SecretKeySpec(fragmentKey, "AES"), GCMParameterSpec(GCM_TAG_BITS, nonce))
            updateAAD(fragmentAad(boundHeader))
        }
        return V2MediaEncryptedFragment(
            header = boundHeader,
            nonceBase64 = Base64.getEncoder().encodeToString(nonce),
            ciphertextBase64 = Base64.getEncoder().encodeToString(cipher.doFinal(plaintext)),
        )
    }

    /** Verifies GCM authentication plus the independent media hash before returning encoded bytes. */
    public fun decryptFragment(fragmentKey: ByteArray, envelope: V2MediaEncryptedFragment): ByteArray {
        require(fragmentKey.size == FRAGMENT_KEY_BYTES) { "v2_media_fragment_key_invalid" }
        val nonce = decodeBase64(envelope.nonceBase64, "v2_media_fragment_authentication_failed")
        val ciphertext = decodeBase64(envelope.ciphertextBase64, "v2_media_fragment_authentication_failed")
        require(nonce.size == GCM_NONCE_BYTES && ciphertext.size >= GCM_TAG_BYTES) {
            "v2_media_fragment_authentication_failed"
        }
        val plaintext = try {
            Cipher.getInstance(AES_GCM_TRANSFORMATION).apply {
                init(Cipher.DECRYPT_MODE, javax.crypto.spec.SecretKeySpec(fragmentKey, "AES"), GCMParameterSpec(GCM_TAG_BITS, nonce))
                updateAAD(fragmentAad(envelope.header))
            }.doFinal(ciphertext)
        } catch (error: Exception) {
            throw IllegalArgumentException("v2_media_fragment_authentication_failed", error)
        }
        val expectedHash = envelope.header.mediaSha256
        require(expectedHash.matches(Regex("[0-9a-f]{64}"))) { "v2_media_fragment_hash_invalid" }
        require(MessageDigest.isEqual(sha256Hex(plaintext).toByteArray(Charsets.US_ASCII), expectedHash.toByteArray(Charsets.US_ASCII))) {
            "v2_media_fragment_payload_hash_mismatch"
        }
        return plaintext
    }

    private fun fragmentAad(header: V2MediaFragmentHeader): ByteArray = (
        "ZHIXING_MEDIA_FRAGMENT_AAD.v1\n" +
            "{" +
            "\"capture_consent_id\":${jsonString(header.captureConsentId)}," +
            "\"capture_epoch\":${header.captureEpoch}," +
            "\"capture_session_id\":${jsonString(header.captureSessionId)}," +
            "\"consent_generation\":${header.consentGeneration}," +
            "\"learner_id\":${jsonString(header.learnerId)}," +
            "\"media_security_session_id\":${jsonString(header.mediaSecuritySessionId)}," +
            "\"media_sha256\":${jsonString(header.mediaSha256)}," +
            "\"pts_end_us\":${header.ptsEndUs}," +
            "\"pts_start_us\":${header.ptsStartUs}," +
            "\"route_epoch\":${header.routeEpoch}," +
            "\"route_lease_id\":${jsonString(header.routeLeaseId)}," +
            "\"sequence\":${header.sequence}" +
            "}\n"
        ).toByteArray(Charsets.UTF_8)

    private fun decodeBase64(value: String, failureCode: String): ByteArray = try {
        require(value.matches(Regex("[A-Za-z0-9+/]+={0,2}"))) { failureCode }
        Base64.getDecoder().decode(value)
    } catch (error: IllegalArgumentException) {
        throw IllegalArgumentException(failureCode, error)
    }

    private fun hkdfSha256(inputKeyMaterial: ByteArray, salt: ByteArray, info: ByteArray): ByteArray {
        val extract = Mac.getInstance("HmacSHA256").apply {
            init(SecretKeySpec(salt, "HmacSHA256"))
        }.doFinal(inputKeyMaterial)
        val expand = Mac.getInstance("HmacSHA256").apply {
            init(SecretKeySpec(extract, "HmacSHA256"))
        }.doFinal(info + byteArrayOf(1))
        return expand.copyOf(FRAGMENT_KEY_BYTES)
    }

    private fun sha256Hex(value: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { byte -> "%02x".format(byte) }

    /** Mirrors Python ``json.dumps(..., ensure_ascii=True, separators=(',', ':'))`` for a string value. */
    private fun jsonString(value: String): String = buildString {
        append('"')
        value.forEach { character ->
            when (character) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (character.code < 0x20 || character.code > 0x7e) {
                    append("\\u")
                    append(character.code.toString(16).padStart(4, '0'))
                } else {
                    append(character)
                }
            }
        }
        append('"')
    }

    private const val FRAGMENT_KEY_BYTES: Int = 32
    private const val HKDF_SALT_BYTES: Int = 32
    private const val GCM_NONCE_BYTES: Int = 12
    private const val GCM_TAG_BYTES: Int = 16
    private const val GCM_TAG_BITS: Int = 128
    private const val AES_GCM_TRANSFORMATION: String = "AES/GCM/NoPadding"
}
