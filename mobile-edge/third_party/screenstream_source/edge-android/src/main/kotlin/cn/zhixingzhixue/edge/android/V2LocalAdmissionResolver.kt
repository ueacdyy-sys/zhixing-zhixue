package cn.zhixingzhixue.edge.android

import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "v2_admission_sessions",
    primaryKeys = ["learnerId", "sessionId"],
    indices = [Index(value = ["learnerId", "captureConsentId", "consentGeneration"], unique = true)],
)
public data class V2AdmissionSessionEntity(
    val learnerId: String,
    val sessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val processingEligibilityGrantId: String,
    val policyBundleHash: String,
    val protocolProfileId: String,
    val active: Boolean,
)

@Entity(tableName = "v2_admission_routes", primaryKeys = ["learnerId", "routeLeaseId"])
public data class V2AdmissionRouteEntity(
    val learnerId: String,
    val routeLeaseId: String,
    val sessionId: String,
    val consentGeneration: Long,
    val routeEpoch: Long,
    val state: String,
)

@Entity(tableName = "v2_admission_scopes", primaryKeys = ["learnerId", "scopeId", "scopeHash"])
public data class V2AdmissionScopeEntity(
    val learnerId: String,
    val scopeId: String,
    val scopeHash: String,
    val sessionId: String,
    val consentGeneration: Long,
    val stable: Boolean,
    val l0ContinuityVerified: Boolean,
    val runtimeRiskClear: Boolean,
)

@Entity(tableName = "v2_admission_audio", primaryKeys = ["learnerId", "audioSnapshotId"])
public data class V2AdmissionAudioEntity(
    val learnerId: String,
    val audioSnapshotId: String,
    val sessionId: String,
    val consentGeneration: Long,
    val resolution: String,
    val semanticAudioDecisionId: String?,
)

/**
 * Local-only authority used before a v2 package can enter Room.
 *
 * A transport decoder is intentionally unable to construct this object.  Its
 * inputs must come from Android-owned session, consent, route, audio and L0
 * ledgers in the same database transaction.
 */
public interface V2LocalAdmissionResolver {
    public suspend fun resolve(
        learnerId: String,
        sessionId: String,
        captureConsentId: String,
        consentGeneration: Long,
        routeLeaseId: String,
        routeEpoch: Long,
        audioSnapshotId: String,
        scopeId: String,
        scopeHash: String,
    ): V2PackageAdmission
}

/** Fails closed until the Android-owned ledgers are wired into Room. */
public class V2AdmissionUnavailableResolver : V2LocalAdmissionResolver {
    override suspend fun resolve(
        learnerId: String,
        sessionId: String,
        captureConsentId: String,
        consentGeneration: Long,
        routeLeaseId: String,
        routeEpoch: Long,
        audioSnapshotId: String,
        scopeId: String,
        scopeHash: String,
    ): V2PackageAdmission = throw IllegalStateException("v2_local_admission_ledger_unavailable")
}
