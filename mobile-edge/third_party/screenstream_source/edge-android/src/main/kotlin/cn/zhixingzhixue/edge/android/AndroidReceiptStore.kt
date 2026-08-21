package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.ReceiptPort
import cn.zhixingzhixue.learning.domain.StudentReceipt
import org.json.JSONArray
import org.json.JSONObject

/** Legacy candidate receipt shell. Existing data is read-only migration evidence. */
public class AndroidReceiptStore(context: Context) : ReceiptPort {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    override suspend fun record(receipt: StudentReceipt) {
        append(receipt)
    }

    public fun append(receipt: StudentReceipt) {
        @Suppress("UNUSED_VARIABLE")
        val rejected = receipt
    }

    private companion object {
        private const val PREFERENCES = "zhixing_mobile_learning"
        private const val RECEIPTS = "receipt_outbox_v1"
    }
}
