package cn.zhixingzhixue.edge.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Phone-owned OpenAI-compatible configuration. The API secret is encrypted
 * with an Android Keystore key and never copied to the paired PC. */
public data class MobileDirectAgentConfig(
    val baseUrl: String,
    val model: String,
    val apiKey: String,
)

/** The execution path is selected by the learner on the phone.  PC pairing is
 * an optional capability, never the implicit prerequisite for an agent chat. */
public enum class AgentExecutionMode { DIRECT_API, PC_GATEWAY, AUTO }

public class MobileDirectAgentProviderStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    public fun read(): MobileDirectAgentConfig? {
        val baseUrl = preferences.getString(KEY_BASE_URL, null)?.trim()?.trimEnd('/') ?: return null
        val model = preferences.getString(KEY_MODEL, null)?.trim() ?: return null
        val encrypted = preferences.getString(KEY_SECRET, null) ?: return null
        val apiKey = runCatching { decrypt(encrypted) }.getOrNull()?.trim().orEmpty()
        return if (baseUrl.isNotBlank() && model.isNotBlank() && apiKey.isNotBlank()) MobileDirectAgentConfig(baseUrl, model, apiKey) else null
    }

    public fun save(baseUrl: String, model: String, apiKey: String) {
        val normalizedUrl = baseUrl.trim().trimEnd('/')
        val normalizedModel = model.trim()
        val normalizedKey = apiKey.trim()
        val uri = runCatching { URI(normalizedUrl) }.getOrNull()
        require(uri?.scheme == "https" && !uri.host.isNullOrBlank()) { "仅接受 HTTPS API 地址" }
        require(normalizedModel.isNotBlank()) { "模型名不能为空" }
        require(normalizedKey.length >= 8) { "API Key 格式无效" }
        preferences.edit()
            .putString(KEY_BASE_URL, normalizedUrl)
            .putString(KEY_MODEL, normalizedModel)
            .putString(KEY_SECRET, encrypt(normalizedKey))
            .commit()
    }

    public fun clear() {
        preferences.edit().remove(KEY_BASE_URL).remove(KEY_MODEL).remove(KEY_SECRET).commit()
    }

    public fun mode(): AgentExecutionMode = runCatching {
        AgentExecutionMode.valueOf(preferences.getString(KEY_MODE, AgentExecutionMode.DIRECT_API.name).orEmpty())
    }.getOrDefault(AgentExecutionMode.DIRECT_API)

    public fun setMode(value: AgentExecutionMode) {
        preferences.edit().putString(KEY_MODE, value.name).commit()
    }

    /** AUTO never silently leaves the selected device.  It is enabled only
     * after the learner explicitly allows fallback in the service page. */
    public fun autoFallbackAllowed(): Boolean = preferences.getBoolean(KEY_AUTO_FALLBACK, false)

    public fun setAutoFallbackAllowed(value: Boolean) {
        preferences.edit().putBoolean(KEY_AUTO_FALLBACK, value).commit()
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val payload = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(payload, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        require(payload.size > IV_BYTES) { "配置密文无效" }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, payload.copyOfRange(0, IV_BYTES)))
        return cipher.doFinal(payload.copyOfRange(IV_BYTES, payload.size)).toString(Charsets.UTF_8)
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        private const val PREFERENCES = "mobile_direct_agent_provider"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_MODEL = "model"
        private const val KEY_SECRET = "secret"
        private const val KEY_MODE = "execution_mode"
        private const val KEY_AUTO_FALLBACK = "allow_auto_fallback"
        private const val KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "zhixing.mobile.direct.agent.v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val IV_BYTES = 12
        private const val TAG_BITS = 128
    }
}

/** A direct mobile fallback for users who have no paired PC/server. */
public class MobileDirectAgentClient {
    public suspend fun test(config: MobileDirectAgentConfig): String = withContext(Dispatchers.IO) {
        val connection = (URI(config.baseUrl + "/models").toURL().openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer ${config.apiKey}")
        }
        try {
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            require(connection.responseCode in 200..299) { "直连 API 返回 HTTP ${connection.responseCode}" }
            val available = JSONObject(response).optJSONArray("data")?.length() ?: 0
            if (available > 0) "连接成功 · 已读取 $available 个模型" else "连接成功 · 服务未返回模型列表"
        } finally {
            connection.disconnect()
        }
    }

    public suspend fun answer(config: MobileDirectAgentConfig, prompt: String): String = withContext(Dispatchers.IO) {
        val endpoint = config.baseUrl + "/chat/completions"
        val connection = (URI(endpoint).toURL().openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer ${config.apiKey}")
        }
        try {
            val body = JSONObject()
                .put("model", config.model)
                .put("temperature", 0.2)
                .put("messages", JSONArray()
                    .put(JSONObject().put("role", "system").put("content", "你是知行智学的学习智能体。基于用户提供的内容回答；没有证据时明确说明。"))
                    .put(JSONObject().put("role", "user").put("content", prompt)))
                .toString()
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            require(connection.responseCode in 200..299) { "直连 API 返回 HTTP ${connection.responseCode}" }
            JSONObject(response).optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")?.optString("content")
                ?.takeIf { it.isNotBlank() } ?: throw IllegalStateException("直连 API 未返回文本")
        } finally {
            connection.disconnect()
        }
    }

    private companion object { private const val TIMEOUT_MS = 65_000 }
}
