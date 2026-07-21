package cn.zhixingzhixue.edge.android

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** Explicit student-controlled local-LAN pairing configuration. */
public data class PcDeliveryLink(
    val baseUrl: String,
    val deviceId: String,
    val pairingToken: String,
    val cursor: String?,
) {
    init {
        require(baseUrl.startsWith("http://") || baseUrl.startsWith("https://")) {
            "pc_delivery_url_required"
        }
        require(deviceId.isNotBlank()) { "pc_delivery_device_id_required" }
        require(pairingToken.isNotBlank()) { "pc_delivery_pairing_token_required" }
    }
}

public class AndroidPcDeliveryLinkStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    public fun read(): PcDeliveryLink? = runCatching {
        val url = preferences.getString(BASE_URL, null) ?: return null
        val deviceId = preferences.getString(DEVICE_ID, null) ?: return null
        val token = preferences.getString(TOKEN, null) ?: return null
        PcDeliveryLink(url, deviceId, token, preferences.getString(CURSOR, null))
    }.getOrNull()

    public fun save(link: PcDeliveryLink) {
        preferences.edit()
            .putString(BASE_URL, link.baseUrl.removeSuffix("/"))
            .putString(DEVICE_ID, link.deviceId)
            .putString(TOKEN, link.pairingToken)
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
) {
    public suspend fun pair(baseUrl: String, pairingToken: String): PcDeliveryLink = withContext(Dispatchers.IO) {
        val normalizedBaseUrl = baseUrl.trim().removeSuffix("/")
        val deviceId = linkStore.localDeviceId()
        val response = anonymousRequest(
            normalizedBaseUrl + "/api/mobile-outbox/devices/pair",
            JSONObject()
                .put("device_id", deviceId)
                .put("pairing_token", pairingToken.trim())
                .toString(),
        )
        val document = JSONObject(response)
        val link = PcDeliveryLink(
            baseUrl = normalizedBaseUrl,
            deviceId = document.getString("device_id"),
            pairingToken = document.getString("access_token"),
            cursor = null,
        )
        linkStore.save(link)
        link
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
            val payload = delivery.getJSONObject("payload")
            require(payload.getString("schema_version") == "mobile_result_message.v1") {
                "mobile_result_message_schema_unsupported"
            }
            require(payload.getString("message_type") == "ANALYSIS_RESULT") {
                "mobile_result_message_type_unsupported"
            }
            inbox.accept(payload.getJSONObject("analysis_result").toString())
            request(
                link.baseUrl + "/api/mobile-outbox/messages/ack",
                "POST",
                link,
                JSONObject().put("device_id", link.deviceId).put("message_id", deliveryId).toString(),
            )
            linkStore.updateCursor(deliveryId)
            accepted += 1
        }
        accepted
    }

    private fun request(url: String, method: String, link: PcDeliveryLink, body: String?): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer " + link.pairingToken)
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
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

    private fun anonymousRequest(url: String, body: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
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
