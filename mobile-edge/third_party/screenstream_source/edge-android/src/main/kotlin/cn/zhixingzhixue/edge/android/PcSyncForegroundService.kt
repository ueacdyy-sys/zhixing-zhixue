package cn.zhixingzhixue.edge.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Student-enabled foreground dataSync service.  It owns the paired-PC polling
 * lifecycle, so delivery continues while the learner is reading or watching in
 * another app.  It is not a hidden background collector and can be stopped by
 * unpairing or Android's normal foreground-service controls.
 */
public class PcSyncForegroundService : Service() {
    private val serviceScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var syncJob: Job? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP || MobileAppServices.pcLinkStore(this).read() == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        promoteToForeground()
        if (syncJob?.isActive != true) {
            syncJob = serviceScope.launch {
                val client = MobileAppServices.pcDeliveryClient(this@PcSyncForegroundService)
                var retryDelayMs = INITIAL_RETRY_DELAY_MS
                while (isActive && MobileAppServices.pcLinkStore(this@PcSyncForegroundService).read() != null) {
                    val result = runCatching { client.synchronizeOnce() }
                    if (result.isSuccess) {
                        retryDelayMs = INITIAL_RETRY_DELAY_MS
                        delay(NORMAL_SYNC_INTERVAL_MS)
                    } else {
                        Log.w(TAG, "Paired-PC synchronization failed; retrying with backoff", result.exceptionOrNull())
                        // If the home PC received a new DHCP address, repair
                        // only a link whose advertised SPKI is already pinned.
                        // This does not silently pair a different LAN device.
                        runCatching { client.reconnectFromNearbyGateway() }
                            .onFailure { error -> Log.d(TAG, "Nearby PC re-discovery unavailable", error) }
                        delay(retryDelayMs)
                        retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                    }
                }
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun promoteToForeground() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "知行智学连接同步", NotificationManager.IMPORTANCE_MIN).apply {
                    description = "已配对 PC 的学习结果同步服务"
                    setShowBadge(false)
                },
            )
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("知行智学正在同步")
            .setContentText("已配对 PC 的候选学习内容会在到达后保存")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    public companion object {
        private const val ACTION_STOP: String = "cn.zhixingzhixue.edge.action.STOP_PC_SYNC"
        private const val CHANNEL_ID: String = "pc_delivery_sync_v1"
        private const val NOTIFICATION_ID: Int = 12041
        private const val TAG: String = "PcSyncForegroundService"
        private const val NORMAL_SYNC_INTERVAL_MS: Long = 15_000
        private const val INITIAL_RETRY_DELAY_MS: Long = 3_000
        private const val MAX_RETRY_DELAY_MS: Long = 60_000

        public fun start(context: Context) {
            if (MobileAppServices.pcLinkStore(context).read() == null) return
            ContextCompat.startForegroundService(context, Intent(context, PcSyncForegroundService::class.java))
        }

        public fun stop(context: Context) {
            context.stopService(Intent(context, PcSyncForegroundService::class.java).setAction(ACTION_STOP))
        }
    }
}
