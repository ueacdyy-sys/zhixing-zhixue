package cn.zhixingzhixue.edge.android

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.time.OffsetDateTime

/** A discoverable PC is not trusted until [PcDeliveryClient.pairDiscovered] succeeds. */
public data class LanGatewayCandidate(
    val baseUrl: String,
    val spkiSha256: String,
    val pairingToken: String,
    val expiresAt: String,
    val deviceName: String,
) {
    public val pairingAddress: String get() = "$baseUrl#spki=sha256/$spkiSha256"
}

/**
 * Small UDP request/reply discovery, rather than a broad LAN scan.  The PC
 * replies unicast to this socket; no Android listener or clear-text HTTP is
 * exposed.  The subsequent HTTPS/SPKI-pinned pairing remains the trust gate.
 */
public class LanGatewayDiscovery {
    public suspend fun discover(timeoutMs: Int = DEFAULT_TIMEOUT_MS): List<LanGatewayCandidate> = withContext(Dispatchers.IO) {
        require(timeoutMs in 250..10_000) { "lan_discovery_timeout_invalid" }
        val candidates = linkedMapOf<String, LanGatewayCandidate>()
        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = timeoutMs.coerceAtMost(1_000)
            val request = DISCOVER_MESSAGE.toByteArray(Charsets.UTF_8)
            socket.send(DatagramPacket(request, request.size, InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT))
            val deadline = System.nanoTime() + timeoutMs * 1_000_000L
            val buffer = ByteArray(4_096)
            while (System.nanoTime() < deadline) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    parse(packet.data.copyOf(packet.length).toString(Charsets.UTF_8))?.let { candidate ->
                        candidates[candidate.baseUrl] = candidate
                    }
                } catch (_: java.net.SocketTimeoutException) {
                    // Keep listening until the bounded discovery interval ends.
                }
            }
        }
        candidates.values.toList()
    }

    private fun parse(raw: String): LanGatewayCandidate? = runCatching {
        val document = JSONObject(raw)
        require(document.getString("type") == "ZHIXING_GATEWAY_ADVERTISEMENT_V1") { "lan_discovery_schema_unsupported" }
        val candidate = LanGatewayCandidate(
            baseUrl = document.getString("base_url"),
            spkiSha256 = document.getString("spki_sha256"),
            pairingToken = document.getString("pairing_token"),
            expiresAt = document.getString("expires_at"),
            deviceName = document.getString("device_name"),
        )
        GatewayTlsConnectionFactory.parsePairingAddress(candidate.pairingAddress)
        require(OffsetDateTime.parse(candidate.expiresAt).isAfter(OffsetDateTime.now())) { "lan_discovery_record_expired" }
        candidate
    }.getOrNull()

    private companion object {
        private const val DISCOVERY_PORT: Int = 39_271
        private const val DEFAULT_TIMEOUT_MS: Int = 2_000
        private const val DISCOVER_MESSAGE: String = "ZHIXING_GATEWAY_DISCOVER_V1"
    }
}
