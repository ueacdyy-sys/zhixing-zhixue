package cn.zhixingzhixue.edge.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import cn.zhixingzhixue.learning.application.CandidateNotice
import cn.zhixingzhixue.learning.application.StudentNotificationPort
import cn.zhixingzhixue.learning.domain.StudentReceiptAction

/**
 * High-importance notification channel for voluntary student review. This asks
 * Android for a heads-up banner; the user's notification settings decide whether
 * it is displayed. The notification never contains an interest/knowledge verdict.
 */
public class AndroidStudentNotice(private val context: Context) : StudentNotificationPort {
    override suspend fun show(notice: CandidateNotice) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "知行智学学习提醒", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "学生自主查看候选证据与选择回执"
            }
        )
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
        builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(notice.title)
            .setContentText(notice.message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(notice.message))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .addAction(action(notice, "保存", StudentReceiptAction.SAVE, 1))
            .addAction(action(notice, "稍后查看", StudentReceiptAction.WATCH_LATER, 2))
            .addAction(action(notice, "关闭", StudentReceiptAction.DISMISS, 3))
        manager.notify(notice.notificationId, builder.build())
    }

    private fun action(
        notice: CandidateNotice,
        label: String,
        action: StudentReceiptAction,
        requestCodeSuffix: Int
    ): NotificationCompat.Action {
        val intent = Intent(context, StudentReceiptReceiver::class.java)
            .setAction(StudentReceiptReceiver.ACTION_RECORD_RECEIPT)
            .putExtra(StudentReceiptReceiver.EXTRA_CAPTURE_ID, notice.candidate.captureId.value)
            .putExtra(StudentReceiptReceiver.EXTRA_ACTION, action.name)
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            notice.notificationId * 10 + requestCodeSuffix,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Action.Builder(null, label, pendingIntent).build()
    }

    private companion object {
        private const val CHANNEL_ID = "student_candidate_notice_v1"
    }
}
