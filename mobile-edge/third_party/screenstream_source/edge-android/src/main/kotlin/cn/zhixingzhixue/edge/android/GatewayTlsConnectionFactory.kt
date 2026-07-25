package cn.zhixingzhixue.edge.android

import android.util.Base64
import java.net.URI
import java.security.MessageDigest
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection

/**
 * The only transport factory allowed to contact a paired PC gateway.
 *
 * The Android platform still performs the normal TLS chain and SAN hostname
 * checks.  After that succeeds, this factory additionally requires the leaf
 * certificate public key to match the SPKI pin shown by the PC during pairing.
 * A URL alone is therefore never a trust decision.
 */
public object GatewayTlsConnectionFactory {
    public data class PairingEndpoint(
        val baseUrl: String,
        val spkiSha256: String,
    )

    public fun parsePairingAddress(rawAddress: String): PairingEndpoint {
        val uri = runCatching { URI(rawAddress.trim()) }
            .getOrElse { throw IllegalArgumentException("pc_pairing_address_invalid") }
        require(uri.scheme.equals("https", ignoreCase = true)) { "pc_delivery_https_required" }
        require(uri.userInfo == null && uri.rawQuery == null) { "pc_pairing_address_components_unsupported" }
        require(uri.host?.isNotBlank() == true) { "pc_pairing_host_required" }
        require(uri.path.isNullOrBlank() || uri.path == "/") { "pc_pairing_path_unsupported" }
        require(uri.port in -1..65535 && uri.port != 0) { "pc_pairing_port_invalid" }
        val pin = uri.rawFragment?.removePrefix("spki=sha256/")
            ?.takeIf { uri.rawFragment.startsWith("spki=sha256/") }
            ?: throw IllegalArgumentException("pc_pairing_spki_pin_required")
        validatePin(pin)
        val host = uri.host
        val authority = if (host.contains(':')) "[$host]" else host
        val canonical = "https://$authority" + if (uri.port > 0) ":${uri.port}" else ""
        return PairingEndpoint(canonical, pin)
    }

    public fun open(link: PcDeliveryLink, url: String, method: String, timeoutMs: Int): HttpsURLConnection {
        val target = runCatching { URI(url) }.getOrElse { throw IllegalArgumentException("pc_gateway_url_invalid") }
        val paired = URI(link.baseUrl)
        require(target.scheme.equals("https", ignoreCase = true)) { "pc_delivery_https_required" }
        require(target.userInfo == null && target.rawFragment == null) { "pc_gateway_url_components_unsupported" }
        require(target.host.equals(paired.host, ignoreCase = true) && effectivePort(target) == effectivePort(paired)) {
            "pc_gateway_origin_mismatch"
        }
        val connection = target.toURL().openConnection() as? HttpsURLConnection
            ?: throw IllegalArgumentException("pc_delivery_https_required")
        connection.requestMethod = method
        connection.connectTimeout = timeoutMs
        connection.readTimeout = timeoutMs
        connection.instanceFollowRedirects = false
        connection.hostnameVerifier = HttpsURLConnection.getDefaultHostnameVerifier()
        return connection
    }

    /** Connect and verify the peer before any request body or response body is processed. */
    public fun connectAndVerify(connection: HttpsURLConnection, spkiSha256: String) {
        connection.connect()
        val expected = decodePin(spkiSha256)
        val certificates = connection.serverCertificates.filterIsInstance<X509Certificate>()
        require(certificates.isNotEmpty()) { "pc_gateway_certificate_missing" }
        val matched = certificates.any { certificate ->
            val actual = MessageDigest.getInstance("SHA-256").digest(certificate.publicKey.encoded)
            MessageDigest.isEqual(actual, expected)
        }
        require(matched) { "pc_gateway_spki_pin_mismatch" }
    }

    public fun validatePin(pin: String) {
        require(runCatching { decodePin(pin) }.isSuccess) { "pc_pairing_spki_pin_invalid" }
    }

    private fun decodePin(pin: String): ByteArray {
        require(pin.matches(Regex("[A-Za-z0-9+/]{43}="))) { "pc_pairing_spki_pin_invalid" }
        val decoded = Base64.decode(pin, Base64.NO_WRAP)
        require(decoded.size == 32) { "pc_pairing_spki_pin_invalid" }
        return decoded
    }

    private fun effectivePort(uri: URI): Int = if (uri.port == -1) 443 else uri.port
}
