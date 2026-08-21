package cn.zhixingzhixue.edge.android

import android.content.Context

/**
 * The learner's durable decision about paired-PC background synchronization.
 *
 * A paired link authenticates a PC; it is not itself permission to restart a
 * previously stopped service after Android recreates the process.
 */
public class PcSyncUserIntent private constructor(
    public val enabled: Boolean,
) {
    public fun permitsServiceStart(hasPairedPc: Boolean): Boolean = enabled && hasPairedPc

    public fun withLearnerStop(): PcSyncUserIntent = disabled()

    public fun withExplicitStart(): PcSyncUserIntent = enabled()

    public companion object {
        /** A missing legacy preference preserves the pre-v2 paired-link behavior once. */
        public fun fromStoredValue(storedEnabled: Boolean?, hasPairedPc: Boolean): PcSyncUserIntent =
            if (storedEnabled ?: hasPairedPc) enabled() else disabled()

        public fun enabled(): PcSyncUserIntent = PcSyncUserIntent(enabled = true)

        public fun disabled(): PcSyncUserIntent = PcSyncUserIntent(enabled = false)
    }
}

/** Persists only the learner's sync choice; credentials remain in their own stores. */
public class PcSyncUserIntentStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    public fun read(hasPairedPc: Boolean): PcSyncUserIntent =
        PcSyncUserIntent.fromStoredValue(
            storedEnabled = if (preferences.contains(KEY_ENABLED)) preferences.getBoolean(KEY_ENABLED, false) else null,
            hasPairedPc = hasPairedPc,
        )

    public fun recordExplicitStart() {
        preferences.edit().putBoolean(KEY_ENABLED, true).commit()
    }

    public fun recordLearnerStop() {
        preferences.edit().putBoolean(KEY_ENABLED, false).commit()
    }

    private companion object {
        private const val PREFERENCES: String = "zhixing_pc_sync_user_intent"
        private const val KEY_ENABLED: String = "enabled"
    }
}

/** Authentication rejection is revocation evidence, never a LAN rediscovery signal. */
public object PcSyncServiceFaultPolicy {
    public fun requiresLearnerStop(errorMessage: String?): Boolean =
        errorMessage == "pc_delivery_http_401" || errorMessage == "pc_delivery_http_403"

    /** A 404 from the capture supervisor means its volatile PC state was lost.
     * It does not revoke the learner's still-live MediaProjection consent. */
    public fun requiresGatewayCaptureRecovery(errorMessage: String?): Boolean =
        errorMessage == "pc_delivery_http_404"
}
