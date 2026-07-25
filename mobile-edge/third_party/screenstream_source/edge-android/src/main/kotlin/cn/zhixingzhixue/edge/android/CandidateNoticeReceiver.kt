package cn.zhixingzhixue.edge.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Base64
import cn.zhixingzhixue.learning.application.CandidateNotice
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Privileged diagnostic bridge for a locally authorized edge analyser.
 *
 * The receiver requires android.permission.DUMP, so ordinary third-party apps
 * cannot issue notices.  It accepts only a candidate evidence prompt; neither
 * interest nor learning conclusions cross this boundary.
 */
public class CandidateNoticeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_SHOW_CANDIDATE_NOTICE) return
        val card = candidateCard(
            raw = intent.getStringExtra(EXTRA_CANDIDATE_CARD_JSON),
            encoded = intent.getStringExtra(EXTRA_CANDIDATE_CARD_B64),
        ) ?: return
        val pendingResult = goAsync()
        val appContext = context.applicationContext
        val windowId = intent.getStringExtra(EXTRA_WINDOW_ID)?.takeIf { it.isNotBlank() }
        val title = intent.getStringExtra(EXTRA_TITLE)?.take(80) ?: "L1 概念小结"
        val message = intent.getStringExtra(EXTRA_MESSAGE)?.take(240) ?: "已为你准备概念小结，点击查看。"
        CoroutineScope(Dispatchers.IO).launch {
            try {
                MobileAppServices.candidateStore(appContext).upsert(card)
                if (card.source == CandidateMediaSource.PHONE_SCREEN && card.isL1Eligible && windowId != null) {
                    // The diagnostic bridge uses the same real L1 delivery
                    // path as the paired-PC inbox. It must not block the
                    // broadcast receiver's main thread while persisting.
                    AndroidStudentNotice(appContext).show(
                        CandidateNotice(
                            notificationId = windowId.hashCode(),
                            candidate = card,
                            title = title,
                            message = message,
                        ),
                    )
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    private fun candidateCard(raw: String?, encoded: String?): CandidateCard? = runCatching {
        val json = raw ?: encoded?.let { token ->
            String(Base64.decode(token, Base64.URL_SAFE or Base64.NO_WRAP), Charsets.UTF_8)
        }
        if (json.isNullOrBlank() || json.length > MAX_CARD_JSON_CHARS) return null
        CandidateCardMessageCodec.decode(JSONObject(json))
    }.getOrNull()

    public companion object {
        public const val ACTION_SHOW_CANDIDATE_NOTICE: String = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"
        public const val EXTRA_WINDOW_ID: String = "window_id"
        public const val EXTRA_TITLE: String = "title"
        public const val EXTRA_MESSAGE: String = "message"
        public const val EXTRA_CANDIDATE_CARD_JSON: String = "candidate_card_json"
        public const val EXTRA_CANDIDATE_CARD_B64: String = "candidate_card_b64"
        public const val EXTRA_CANDIDATE_CARD_ID: String = "candidate_card_id"
        public const val EXTRA_OPEN_L1: String = "open_l1"
        private const val MAX_CARD_JSON_CHARS: Int = 12_000
    }
}
