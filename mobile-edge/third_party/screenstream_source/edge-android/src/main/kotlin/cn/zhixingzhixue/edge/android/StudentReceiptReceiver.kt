package cn.zhixingzhixue.edge.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.StudentReceipt
import cn.zhixingzhixue.learning.domain.StudentReceiptAction
import java.time.OffsetDateTime

/** Receipts are explicit student actions, persisted locally before later local-hub export. */
public class StudentReceiptReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_RECORD_RECEIPT) return
        val captureId = intent.getStringExtra(EXTRA_CAPTURE_ID)?.takeIf { it.isNotBlank() } ?: return
        val action = intent.getStringExtra(EXTRA_ACTION)?.let { value ->
            runCatching { StudentReceiptAction.valueOf(value) }.getOrNull()
        } ?: return
        AndroidReceiptStore(context).append(
            StudentReceipt(
                captureId = CaptureId(captureId),
                evidenceCardId = null,
                action = action,
                recordedAt = OffsetDateTime.now()
            )
        )
    }

    public companion object {
        public const val ACTION_RECORD_RECEIPT: String = "cn.zhixingzhixue.edge.action.RECORD_RECEIPT"
        public const val EXTRA_CAPTURE_ID: String = "capture_id"
        public const val EXTRA_ACTION: String = "receipt_action"
    }
}
