package cn.zhixingzhixue.edge.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Retained only as a constants holder during migration.
 *
 * It is not registered in the manifest and a v1 candidate must never persist
 * content or create an Android notification through this class.
 */
public class CandidateNoticeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // The old broadcast protocol is intentionally a no-op.
    }

    public companion object {
        public const val ACTION_SHOW_CANDIDATE_NOTICE: String = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"
        public const val EXTRA_WINDOW_ID: String = "window_id"
        public const val EXTRA_TITLE: String = "title"
        public const val EXTRA_MESSAGE: String = "message"
        public const val EXTRA_CANDIDATE_CARD_JSON: String = "candidate_card_json"
        public const val EXTRA_CANDIDATE_CARD_B64: String = "candidate_card_b64"
        public const val EXTRA_CANDIDATE_CARD_ID: String = "candidate_card_id"
        public const val EXTRA_OPEN_L1: String = "open_l1"
    }
}
