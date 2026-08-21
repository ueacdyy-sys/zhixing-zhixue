package cn.zhixingzhixue.edge.android

import android.accessibilityservice.AccessibilityService
import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.Build
import android.os.Process
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/** A minimal, package-name-only observation emitted by a user-enabled source. */
public data class ForegroundAppObservation(
    val packageName: String,
    val source: ForegroundAppObservationSource,
    val observedElapsedRealtimeMs: Long,
)

/**
 * Process-local bridge between the system Accessibility service and the
 * student-controlled capture service.  No view hierarchy, text, interaction,
 * gesture or third-party action is exposed through this bridge.
 */
public object ForegroundAppObservationBus {
    private val mutableObservations: MutableSharedFlow<ForegroundAppObservation> = MutableSharedFlow(
        replay = 0,
        extraBufferCapacity = 16,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )

    public val observations: SharedFlow<ForegroundAppObservation> = mutableObservations.asSharedFlow()

    public fun report(packageName: String, source: ForegroundAppObservationSource, observedElapsedRealtimeMs: Long) {
        if (packageName.isBlank()) return
        mutableObservations.tryEmit(ForegroundAppObservation(packageName, source, observedElapsedRealtimeMs))
    }
}

/**
 * Optional observation source. Android shows this service in system settings;
 * it becomes active only after the learner explicitly enables it. Its sole
 * output is the foreground application package name.
 */
public class SelectedAppForegroundAccessibilityService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val safeEvent = event ?: return
        if (safeEvent.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val packageName = safeEvent.packageName?.toString()?.trim().orEmpty()
        ForegroundAppObservationBus.report(
            packageName,
            ForegroundAppObservationSource.ACCESSIBILITY,
            android.os.SystemClock.elapsedRealtime(),
        )
    }

    override fun onInterrupt(): Unit = Unit
}

/** Usage-access fallback for devices on which the learner does not enable Accessibility. */
public class UsageStatsForegroundAppObserver(private val context: Context) {
    public fun hasUsageAccess(): Boolean {
        val appOps = context.getSystemService(AppOpsManager::class.java)
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
        } else {
            @Suppress("DEPRECATION")
            appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    /** Most recent foreground package since [fromWallClockMs], or null when permission/data is unavailable. */
    public fun mostRecentForegroundPackage(fromWallClockMs: Long, toWallClockMs: Long = System.currentTimeMillis()): String? {
        if (!hasUsageAccess()) return null
        val manager = context.getSystemService(UsageStatsManager::class.java)
        val events = manager.queryEvents(fromWallClockMs, toWallClockMs)
        val event = UsageEvents.Event()
        var mostRecent: String? = null
        var mostRecentTimestamp = Long.MIN_VALUE
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (
                event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND ||
                (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && event.eventType == UsageEvents.Event.ACTIVITY_RESUMED)
            ) {
                val packageName = event.packageName?.trim().orEmpty()
                if (packageName.isNotBlank() && event.timeStamp >= mostRecentTimestamp) {
                    mostRecent = packageName
                    mostRecentTimestamp = event.timeStamp
                }
            }
        }
        return mostRecent
    }

    /** Used only to let the learner choose a whitelist from their own recent applications. */
    public fun recentlyForegroundPackages(lookbackMs: Long = 30L * 24 * 60 * 60 * 1000): List<String> {
        if (!hasUsageAccess()) return emptyList()
        val manager = context.getSystemService(UsageStatsManager::class.java)
        return manager.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, System.currentTimeMillis() - lookbackMs, System.currentTimeMillis())
            .asSequence()
            .filter { it.lastTimeUsed > 0L && it.packageName.isNotBlank() && it.packageName != context.packageName }
            .sortedByDescending { it.lastTimeUsed }
            .map { it.packageName }
            .distinct()
            .take(12)
            .toList()
    }
}
