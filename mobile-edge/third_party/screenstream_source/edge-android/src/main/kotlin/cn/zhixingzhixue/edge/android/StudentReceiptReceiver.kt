package cn.zhixingzhixue.edge.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
/** Legacy candidate receiver retained only for binary compatibility; it has no production side effect. */
public class StudentReceiptReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // v1 candidate receipts cannot enter interest, profile or transport paths.
    }

    public companion object {
        public const val ACTION_RECORD_RECEIPT: String = "cn.zhixingzhixue.edge.action.RECORD_RECEIPT"
        public const val EXTRA_CAPTURE_ID: String = "capture_id"
        public const val EXTRA_CANDIDATE_CARD_ID: String = "candidate_card_id"
        public const val EXTRA_ACTION: String = "receipt_action"
    }
}
