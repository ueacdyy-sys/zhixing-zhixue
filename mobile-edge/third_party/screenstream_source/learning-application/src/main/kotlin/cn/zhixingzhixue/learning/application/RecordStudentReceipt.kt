package cn.zhixingzhixue.learning.application

import cn.zhixingzhixue.learning.domain.StudentReceipt

public class RecordStudentReceipt(private val receiptPort: ReceiptPort) {
    public suspend operator fun invoke(receipt: StudentReceipt): Unit = receiptPort.record(receipt)
}
