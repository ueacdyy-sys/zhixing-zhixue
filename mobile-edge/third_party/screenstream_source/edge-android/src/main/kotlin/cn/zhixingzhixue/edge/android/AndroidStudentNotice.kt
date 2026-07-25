package cn.zhixingzhixue.edge.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.Person
import androidx.core.graphics.drawable.IconCompat
import cn.zhixingzhixue.edge.android.R
import cn.zhixingzhixue.learning.application.CandidateNotice
import cn.zhixingzhixue.learning.application.StudentNotificationPort
import cn.zhixingzhixue.learning.domain.StudentReceiptAction

/**
 * High-importance Android conversation notification for a PC-prepared L1
 * concept brief. This asks Android for a heads-up banner; the user's
 * notification settings decide whether it is displayed. L0 stays only as
 * candidate evidence inside the app and never posts a heads-up notification.
 */
public class AndroidStudentNotice(private val context: Context) : StudentNotificationPort {
    override suspend fun show(notice: CandidateNotice) {
        val manager = ensureChannel()
        val assistant = Person.Builder()
            .setName(SENDER_NAME)
            .setBot(true)
            .setIcon(IconCompat.createWithResource(context, R.drawable.ic_zhixing_message_24dp))
            .build()
        val messageStyle = NotificationCompat.MessagingStyle(assistant)
            .setConversationTitle(CONVERSATION_TITLE)
            .setGroupConversation(false)
            .addMessage(notice.message, System.currentTimeMillis(), assistant)
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
        builder
            .setSmallIcon(R.drawable.ic_zhixing_message_24dp)
            .setContentText(notice.message)
            .setStyle(messageStyle)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setContentIntent(openCandidate(notice))
            .addAction(action(notice, "稍后查看", StudentReceiptAction.WATCH_LATER, 1))
        manager.notify(NOTIFICATION_TAG, notice.notificationId, builder.build())
    }

    /**
     * Registers the L1 learning-message channel without posting a notification.
     * This keeps the in-app system-notification settings link valid before the
     * first evidence message arrives.
     */
    public fun ensureChannel(): NotificationManager {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "学习消息", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "L1 概念小结到达时的系统消息通知"
                    enableVibration(true)
                }
            )
        }
        return manager
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
            .putExtra(StudentReceiptReceiver.EXTRA_CANDIDATE_CARD_ID, notice.candidate.id.value)
            .putExtra(StudentReceiptReceiver.EXTRA_ACTION, action.name)
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            notice.notificationId * 10 + requestCodeSuffix,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Action.Builder(null, label, pendingIntent).build()
    }

    private fun openCandidate(notice: CandidateNotice): PendingIntent? {
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            putExtra(CandidateNoticeReceiver.EXTRA_CANDIDATE_CARD_ID, notice.candidate.id.value)
            putExtra(CandidateNoticeReceiver.EXTRA_OPEN_L1, true)
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        } ?: return null
        return PendingIntent.getActivity(
            context,
            notice.notificationId,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    internal companion object {
        /** Versioned so old reminder-channel preferences cannot mask L1 message delivery. */
        internal const val CHANNEL_ID = "student_l1_messages_v4"
        private const val NOTIFICATION_TAG = "candidate-card"
        private const val SENDER_NAME = "知行智学"
        private const val CONVERSATION_TITLE = "学习消息"
    }
}
