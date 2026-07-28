package cn.zhixingzhixue.edge.android

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Process-scoped ownership of the active paired-PC capture session.
 *
 * The RTSP service outlives an individual Compose route.  Keeping this fact in
 * a connection-page `rememberSaveable` value caused a route change to forget a
 * live PC worker and create a second one when the user returned.  This
 * coordinator intentionally owns only the current session id; the PC gateway
 * remains authoritative for the worker state.
 */
public class PcCaptureSessionCoordinator {
    private val mutableActiveSessionId: MutableStateFlow<String?> = MutableStateFlow(null)
    public val activeSessionId: StateFlow<String?> = mutableActiveSessionId.asStateFlow()

    public fun activate(sessionId: String) {
        require(sessionId.isNotBlank()) { "capture_session_id_required" }
        mutableActiveSessionId.value = sessionId
    }

    public fun clear(sessionId: String? = null) {
        if (sessionId == null || mutableActiveSessionId.value == sessionId) {
            mutableActiveSessionId.value = null
        }
    }
}
