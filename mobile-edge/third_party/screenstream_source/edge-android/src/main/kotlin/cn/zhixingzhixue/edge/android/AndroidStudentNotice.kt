package cn.zhixingzhixue.edge.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import cn.zhixingzhixue.learning.application.CandidateNotice
import cn.zhixingzhixue.learning.application.StudentNotificationPort

/**
 * Legacy candidate notification adapter retained only for the Android channel
 * settings entry during migration. Candidate v1 data cannot post a system
 * notification. A future v2 worker must use its own nonce-gated Room outbox.
 */
public class AndroidStudentNotice(private val context: Context) : StudentNotificationPort {
    override suspend fun show(notice: CandidateNotice) {
        @Suppress("UNUSED_VARIABLE")
        val rejected = notice
        throw IllegalStateException("legacy_candidate_notification_disabled")
    }

    /** Registers a settings channel only; it does not declare v2 delivery available. */
    public fun ensureChannel(): NotificationManager {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "学习消息", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "学习消息的系统设置入口；旧候选卡不会投递"
                    enableVibration(true)
                }
            )
        }
        return manager
    }

    internal companion object {
        internal const val CHANNEL_ID = "student_l1_messages_v4"
    }
}
