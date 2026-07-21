package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.ReceiptPort
import cn.zhixingzhixue.learning.domain.StudentReceipt
import org.json.JSONArray
import org.json.JSONObject

/** Append-only local receipt outbox; transmission is deliberately a later adapter. */
public class AndroidReceiptStore(context: Context) : ReceiptPort {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    override suspend fun record(receipt: StudentReceipt) {
        append(receipt)
    }

    public fun append(receipt: StudentReceipt) {
        val values = JSONArray(preferences.getString(RECEIPTS, "[]"))
        values.put(
            JSONObject()
                .put("captureId", receipt.captureId?.value)
                .put("evidenceCardId", receipt.evidenceCardId?.value)
                .put("candidateCardId", receipt.candidateCardId?.value)
                .put("action", receipt.action.name)
                .put("recordedAt", receipt.recordedAt.toString())
        )
        preferences.edit().putString(RECEIPTS, values.toString()).apply()
    }

    private companion object {
        private const val PREFERENCES = "zhixing_mobile_learning"
        private const val RECEIPTS = "receipt_outbox_v1"
    }
}
