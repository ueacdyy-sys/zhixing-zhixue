package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.SessionPort
import cn.zhixingzhixue.learning.domain.MobileLearningSession
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.MobileSessionStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.OffsetDateTime
import java.util.UUID

/** A student-controlled local session; it does not create or drive any PC task. */
public class AndroidMobileSessionStore(context: Context) : SessionPort {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    override val current: StateFlow<MobileLearningSession?> = MutableStateFlow(read())

    override suspend fun open(): MobileLearningSession {
        val session = MobileLearningSession(MobileSessionId(UUID.randomUUID().toString()), OffsetDateTime.now(), MobileSessionStatus.ACTIVE)
        save(session)
        (current as MutableStateFlow).value = session
        return session
    }

    override suspend fun close() {
        preferences.edit().remove(SESSION_ID).remove(STARTED_AT).apply()
        (current as MutableStateFlow).value = null
    }

    private fun read(): MobileLearningSession? = runCatching {
        val id = preferences.getString(SESSION_ID, null) ?: return null
        val startedAt = preferences.getString(STARTED_AT, null) ?: return null
        MobileLearningSession(MobileSessionId(id), OffsetDateTime.parse(startedAt), MobileSessionStatus.ACTIVE)
    }.getOrNull()

    private fun save(session: MobileLearningSession) {
        preferences.edit().putString(SESSION_ID, session.id.value).putString(STARTED_AT, session.startedAt.toString()).apply()
    }

    private companion object {
        private const val PREFERENCES = "zhixing_mobile_learning"
        private const val SESSION_ID = "session_id_v1"
        private const val STARTED_AT = "session_started_at_v1"
    }
}
