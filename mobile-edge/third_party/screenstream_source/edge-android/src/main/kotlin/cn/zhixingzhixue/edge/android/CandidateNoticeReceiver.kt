package cn.zhixingzhixue.edge.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat

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
        val windowId = intent.getStringExtra(EXTRA_WINDOW_ID)?.takeIf { it.isNotBlank() } ?: return
        val title = intent.getStringExtra(EXTRA_TITLE)?.take(80) ?: "发现一段可回看内容"
        val message = intent.getStringExtra(EXTRA_MESSAGE)?.take(240) ?: "已形成候选证据，可自主查看。"
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "知行智学学习提醒", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "基于当前浏览内容的候选证据提醒"
            }
        )
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val pendingIntent = launch?.let {
            PendingIntent.getActivity(
                context,
                windowId.hashCode(),
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
        manager.notify(windowId.hashCode(), notification)
    }

    public companion object {
        public const val ACTION_SHOW_CANDIDATE_NOTICE: String = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"
        public const val EXTRA_WINDOW_ID: String = "window_id"
        public const val EXTRA_TITLE: String = "title"
        public const val EXTRA_MESSAGE: String = "message"
        private const val CHANNEL_ID: String = "student_candidate_notice_v1"
    }
}
