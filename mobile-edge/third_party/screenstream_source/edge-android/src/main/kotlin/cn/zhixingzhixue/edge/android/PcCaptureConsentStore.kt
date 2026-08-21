package cn.zhixingzhixue.edge.android

import android.content.Context
import java.util.UUID

/**
 * The learner-scoped capture identity is separate from the paired device id.
 * A new snapshot is issued only for the explicit Start action; switching
 * videos or foreground apps never creates another consent.
 */
public data class PcCaptureConsentSnapshot(
    val learnerId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val captureEpoch: Long,
) {
    init {
        require(learnerId.isNotBlank() && !learnerId.startsWith("android-")) {
            "capture_learner_identity_invalid"
        }
        require(captureConsentId.isNotBlank() && consentGeneration > 0L && captureEpoch > 0L) {
            "capture_consent_snapshot_invalid"
        }
    }
}

public class PcCaptureConsentStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** Creates or advances one explicit user capture snapshot. */
    public fun beginExplicitCapture(): PcCaptureConsentSnapshot {
        val previousGeneration = preferences.getLong(CONSENT_GENERATION, 0L)
        val learnerId = preferences.getString(LEARNER_ID, null)?.takeIf { it.isNotBlank() }
            ?: "learner-" + UUID.randomUUID().toString()
        val snapshot = PcCaptureConsentSnapshot(
            learnerId = learnerId,
            captureConsentId = "consent-" + UUID.randomUUID().toString(),
            consentGeneration = previousGeneration + 1L,
            captureEpoch = previousGeneration + 1L,
        )
        preferences.edit()
            .putString(LEARNER_ID, snapshot.learnerId)
            .putString(CONSENT_ID, snapshot.captureConsentId)
            .putLong(CONSENT_GENERATION, snapshot.consentGeneration)
            .putLong(CAPTURE_EPOCH, snapshot.captureEpoch)
            .commit()
        return snapshot
    }

    public fun current(): PcCaptureConsentSnapshot? = runCatching {
        PcCaptureConsentSnapshot(
            learnerId = preferences.getString(LEARNER_ID, null) ?: return null,
            captureConsentId = preferences.getString(CONSENT_ID, null) ?: return null,
            consentGeneration = preferences.getLong(CONSENT_GENERATION, 0L),
            captureEpoch = preferences.getLong(CAPTURE_EPOCH, 0L),
        )
    }.getOrNull()

    public fun clearAfterRevoke() {
        preferences.edit().remove(CONSENT_ID).remove(CONSENT_GENERATION).remove(CAPTURE_EPOCH).commit()
    }

    private companion object {
        private const val PREFERENCES = "zhixing_capture_consent"
        private const val LEARNER_ID = "learner_id"
        private const val CONSENT_ID = "capture_consent_id"
        private const val CONSENT_GENERATION = "consent_generation"
        private const val CAPTURE_EPOCH = "capture_epoch"
    }
}
