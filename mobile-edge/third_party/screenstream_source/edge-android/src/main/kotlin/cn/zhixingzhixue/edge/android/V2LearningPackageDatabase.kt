package cn.zhixingzhixue.edge.android

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Update
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID

/**
 * Room persistence boundary for `CONTENT_ANALYSIS_PACKAGE.v2.l1`.
 *
 * This database is intentionally separate from candidate SharedPreferences and
 * legacy graph SQLite stores. A package is either stored together with its
 * moment, revision, L1 brief, Discover record, receipt and notification outbox
 * row, or none of them are stored. The caller must validate transport/schema,
 * learner scope, consent and route before constructing [V2PackageIngress].
 */
@Entity(
    tableName = "v2_content_packages",
    primaryKeys = ["learnerId", "packageId", "packageRevisionId"],
    indices = [Index(value = ["messageId"], unique = true)],
)
public data class V2ContentPackageEntity(
    val learnerId: String,
    val packageId: String,
    val packageRevisionId: String,
    val messageId: String,
    val sessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val processingEligibilityGrantId: String,
    val policyBundleHash: String,
    val protocolProfileId: String,
    val analysisRouteLeaseId: String,
    val routeEpoch: Long,
    val audioSnapshotId: String,
    val audioResolution: String,
    val semanticAudioDecisionId: String?,
    val episodeId: String,
    val momentId: String,
    val momentRevisionId: String,
    val scopeId: String,
    val scopeHash: String,
    val payloadHash: String,
    val payloadJson: String,
    val receivedElapsedNs: Long,
)

@Entity(
    tableName = "v2_learning_moments",
    primaryKeys = ["learnerId", "momentId"],
    indices = [Index(value = ["learnerId", "episodeId", "semanticLineageId", "learningAnchorId"], unique = true)],
)
public data class V2LearningMomentEntity(
    val learnerId: String,
    val momentId: String,
    val sessionId: String,
    val episodeId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val semanticLineageId: String,
    val learningAnchorId: String,
    val interventionKey: String,
    val currentRevisionId: String,
    val state: String,
    val createdElapsedNs: Long,
)

@Entity(
    tableName = "v2_learning_moment_revisions",
    primaryKeys = ["learnerId", "momentRevisionId"],
    indices = [Index(value = ["learnerId", "momentId", "revisionNumber"], unique = true)],
)
public data class V2LearningMomentRevisionEntity(
    val learnerId: String,
    val momentRevisionId: String,
    val momentId: String,
    val revisionNumber: Long,
    val replacesRevisionId: String?,
    val scopeId: String,
    val scopeHash: String,
    val scopeSemanticRevision: Long,
    val interestAssessmentId: String,
    val learningOfferAssessmentId: String,
    val evidenceHash: String,
    val revisionReason: String,
    val createdElapsedNs: Long,
)

@Entity(tableName = "v2_l1_briefs", primaryKeys = ["learnerId", "briefId"])
public data class V2L1BriefEntity(
    val learnerId: String,
    val briefId: String,
    val momentId: String,
    val scopeId: String,
    val interventionKey: String,
    val title: String,
    val summary: String,
    val evidenceHash: String,
    val accessState: String,
)

@Entity(
    tableName = "v2_discover_entries",
    primaryKeys = ["learnerId", "momentId"],
)
public data class V2DiscoverEntryEntity(
    val learnerId: String,
    val momentId: String,
    val packageId: String,
    val packageRevisionId: String,
    val briefId: String,
    val recordedElapsedNs: Long,
)

@Entity(
    tableName = "v2_package_receipts",
    primaryKeys = ["learnerId", "packageId", "packageRevisionId"],
    indices = [Index(value = ["receiptId"], unique = true), Index(value = ["idempotencyKey"], unique = true)],
)
public data class V2PackageReceiptEntity(
    val learnerId: String,
    val packageId: String,
    val packageRevisionId: String,
    val receiptMessageId: String,
    val receiptId: String,
    val idempotencyKey: String,
    val createdAt: String,
    val sessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val processingEligibilityGrantId: String,
    val policyBundleHash: String,
    val protocolProfileId: String,
    val deliveredMessageId: String,
    val deliveryLeaseId: String,
    val packagePayloadHash: String,
    val transactionHash: String,
    val persistedElapsedNs: Long,
    val disposition: String,
)

@Entity(
    tableName = "v2_notification_outbox",
    primaryKeys = ["learnerId", "interventionKey"],
    indices = [Index(value = ["learnerId", "briefId"])],
)
public data class V2NotificationOutboxEntity(
    val learnerId: String,
    val interventionKey: String,
    val briefId: String,
    val momentId: String,
    val packageRevisionId: String,
    val state: String,
    val createdElapsedNs: Long,
)

/** Fully validated transport payload in Room-friendly form. */
public data class V2PackageIngress(
    val packageEntity: V2ContentPackageEntity,
    /** Transport lease, distinct from [V2ContentPackageEntity.analysisRouteLeaseId]. */
    val deliveryLeaseId: String,
    val momentEntity: V2LearningMomentEntity,
    val momentRevisionEntity: V2LearningMomentRevisionEntity,
    val briefEntity: V2L1BriefEntity,
    val discoverEntryEntity: V2DiscoverEntryEntity,
)

public enum class V2PackagePersistState {
    PERSISTED,
    ALREADY_PERSISTED,
}

/** Snapshot resolved from Android's local, learner-scoped admission ledger. */
public data class V2PackageAdmission(
    val learnerId: String,
    val sessionId: String,
    val captureConsentId: String,
    val consentGeneration: Long,
    val processingEligibilityGrantId: String,
    val policyBundleHash: String,
    val protocolProfileId: String,
    val routeLeaseId: String,
    val routeEpoch: Long,
    val routeState: V2LocalRouteState,
    val audioSnapshotId: String,
    val audioResolution: String,
    val semanticAudioDecisionId: String?,
    val scopeId: String,
    val scopeHash: String,
    val scopeStable: Boolean,
    val l0ContinuityVerified: Boolean,
    val runtimeRiskClear: Boolean,
)

public enum class V2LocalRouteState { PC_LOCAL_ACTIVE, PC_BUFFER_ONLY, CLOUD_ACTIVE, UNAVAILABLE, CLOSED, REVOKED }

/**
 * L1 admission is denied unless the payload agrees with locally resolved
 * evidence. This is deliberately separate from package self-consistency: a
 * paired PC cannot self-authorize an expired consent or a different route.
 */
public object V2PackageAdmissionGate {
    public fun validate(ingress: V2PackageIngress, local: V2PackageAdmission) {
        val packageValue = ingress.packageEntity
        require(
            packageValue.processingEligibilityGrantId.isNotBlank() &&
                packageValue.policyBundleHash.isNotBlank() &&
                packageValue.protocolProfileId.isNotBlank()
        ) { "v2_local_grant_or_policy_missing" }
        require(
            packageValue.learnerId == local.learnerId &&
                packageValue.sessionId == local.sessionId &&
                packageValue.captureConsentId == local.captureConsentId &&
                packageValue.consentGeneration == local.consentGeneration &&
                packageValue.processingEligibilityGrantId == local.processingEligibilityGrantId &&
                packageValue.policyBundleHash == local.policyBundleHash &&
                packageValue.protocolProfileId == local.protocolProfileId
        ) { "v2_local_session_or_consent_mismatch" }
        require(
            packageValue.analysisRouteLeaseId == local.routeLeaseId &&
                packageValue.routeEpoch == local.routeEpoch &&
                local.routeState == V2LocalRouteState.PC_LOCAL_ACTIVE
        ) { "v2_local_route_lease_denied" }
        require(
            packageValue.audioSnapshotId == local.audioSnapshotId &&
                packageValue.audioResolution == local.audioResolution &&
                packageValue.semanticAudioDecisionId == local.semanticAudioDecisionId
        ) { "v2_local_audio_snapshot_mismatch" }
        require(packageValue.scopeId == local.scopeId && packageValue.scopeHash == local.scopeHash) {
            "v2_local_scope_mismatch"
        }
        require(local.scopeStable && local.l0ContinuityVerified && local.runtimeRiskClear) {
            "v2_local_l0_or_risk_gate_denied"
        }
    }
}

/**
 * Pure ingress invariant gate shared by the Room transaction and JVM tests.
 *
 * The PC codec performs richer semantic and policy validation.  This gate is
 * deliberately narrower: it makes it impossible for a structurally valid
 * payload to cross a learner, session, consent, moment or revision boundary
 * after it has reached Android persistence.
 */
internal object V2PackageIngressIntegrity {
    internal fun validate(ingress: V2PackageIngress) {
        val packageValue = ingress.packageEntity
        val moment = ingress.momentEntity
        val revision = ingress.momentRevisionEntity
        val brief = ingress.briefEntity
        val discover = ingress.discoverEntryEntity

        require(ingress.deliveryLeaseId.isNotBlank()) { "v2_package_delivery_lease_missing" }

        require(packageValue.learnerId == moment.learnerId && packageValue.learnerId == revision.learnerId) {
            "v2_package_learner_mismatch"
        }
        require(
            packageValue.sessionId == moment.sessionId &&
                packageValue.episodeId == moment.episodeId &&
                packageValue.captureConsentId == moment.captureConsentId &&
                packageValue.consentGeneration == moment.consentGeneration
        ) { "v2_package_session_or_consent_mismatch" }
        require(
            revision.learnerId == moment.learnerId &&
                revision.momentId == moment.momentId &&
                packageValue.momentId == moment.momentId &&
                packageValue.momentRevisionId == revision.momentRevisionId &&
                packageValue.scopeId == revision.scopeId &&
                packageValue.scopeHash == revision.scopeHash &&
                moment.currentRevisionId == revision.momentRevisionId
        ) { "v2_package_moment_revision_mismatch" }
        require(
            packageValue.learnerId == brief.learnerId &&
                packageValue.momentId == brief.momentId &&
                packageValue.scopeId == brief.scopeId &&
                moment.interventionKey == brief.interventionKey
        ) { "v2_package_brief_mismatch" }
        require(
            discover.learnerId == packageValue.learnerId &&
                discover.momentId == moment.momentId &&
                discover.packageId == packageValue.packageId &&
                discover.packageRevisionId == packageValue.packageRevisionId &&
                discover.briefId == brief.briefId
        ) { "v2_package_discover_mismatch" }
    }

    internal fun requireSameMomentBrief(previous: V2L1BriefEntity, incoming: V2L1BriefEntity) {
        require(previous.momentId == incoming.momentId && previous.briefId == incoming.briefId) {
            "v2_moment_brief_identity_conflict"
        }
    }
}

@Dao
public abstract class V2LearningPackageDao {
    @Query("SELECT * FROM v2_admission_sessions WHERE learnerId = :learnerId AND sessionId = :sessionId")
    internal abstract suspend fun admissionSession(learnerId: String, sessionId: String): V2AdmissionSessionEntity?

    @Query("SELECT * FROM v2_admission_routes WHERE learnerId = :learnerId AND routeLeaseId = :leaseId")
    internal abstract suspend fun admissionRoute(learnerId: String, leaseId: String): V2AdmissionRouteEntity?

    @Query("SELECT * FROM v2_admission_scopes WHERE learnerId = :learnerId AND scopeId = :scopeId AND scopeHash = :scopeHash")
    internal abstract suspend fun admissionScope(learnerId: String, scopeId: String, scopeHash: String): V2AdmissionScopeEntity?

    @Query("SELECT * FROM v2_admission_audio WHERE learnerId = :learnerId AND audioSnapshotId = :audioSnapshotId")
    internal abstract suspend fun admissionAudio(learnerId: String, audioSnapshotId: String): V2AdmissionAudioEntity?

    @Transaction
    internal open suspend fun resolveAdmission(ingress: V2PackageIngress): V2PackageAdmission {
        val value = ingress.packageEntity
        val session = admissionSession(value.learnerId, value.sessionId)
            ?: throw IllegalStateException("v2_local_session_missing")
        val route = admissionRoute(value.learnerId, value.analysisRouteLeaseId)
            ?: throw IllegalStateException("v2_local_route_missing")
        val scope = admissionScope(value.learnerId, value.scopeId, value.scopeHash)
            ?: throw IllegalStateException("v2_local_scope_missing")
        val audio = admissionAudio(value.learnerId, value.audioSnapshotId)
            ?: throw IllegalStateException("v2_local_audio_missing")
        require(session.active && session.captureConsentId == value.captureConsentId && session.consentGeneration == value.consentGeneration) { "v2_local_consent_denied" }
        require(
            value.processingEligibilityGrantId.isNotBlank() &&
                value.policyBundleHash.isNotBlank() &&
                value.protocolProfileId.isNotBlank() &&
                session.processingEligibilityGrantId.isNotBlank() &&
                session.policyBundleHash.isNotBlank() &&
                session.protocolProfileId.isNotBlank()
        ) { "v2_local_grant_or_policy_missing" }
        require(
            session.processingEligibilityGrantId == value.processingEligibilityGrantId &&
                session.policyBundleHash == value.policyBundleHash &&
                session.protocolProfileId == value.protocolProfileId
        ) { "v2_local_grant_or_policy_denied" }
        require(route.sessionId == value.sessionId && route.consentGeneration == value.consentGeneration) { "v2_local_route_binding_denied" }
        require(scope.sessionId == value.sessionId && scope.consentGeneration == value.consentGeneration) { "v2_local_scope_binding_denied" }
        require(audio.sessionId == value.sessionId && audio.consentGeneration == value.consentGeneration) { "v2_local_audio_binding_denied" }
        return V2PackageAdmission(
            value.learnerId, value.sessionId, value.captureConsentId, value.consentGeneration,
            session.processingEligibilityGrantId, session.policyBundleHash, session.protocolProfileId,
            route.routeLeaseId, route.routeEpoch, V2LocalRouteState.valueOf(route.state),
            audio.audioSnapshotId, audio.resolution, audio.semanticAudioDecisionId,
            scope.scopeId, scope.scopeHash, scope.stable, scope.l0ContinuityVerified, scope.runtimeRiskClear,
        )
    }

    @Query("SELECT * FROM v2_content_packages WHERE learnerId = :learnerId AND packageId = :packageId AND packageRevisionId = :packageRevisionId")
    protected abstract suspend fun findPackage(
        learnerId: String,
        packageId: String,
        packageRevisionId: String,
    ): V2ContentPackageEntity?

    @Query("SELECT * FROM v2_learning_moments WHERE learnerId = :learnerId AND momentId = :momentId")
    protected abstract suspend fun findMoment(learnerId: String, momentId: String): V2LearningMomentEntity?

    @Query("SELECT * FROM v2_learning_moment_revisions WHERE learnerId = :learnerId AND momentRevisionId = :revisionId")
    protected abstract suspend fun findMomentRevision(learnerId: String, revisionId: String): V2LearningMomentRevisionEntity?

    @Query("SELECT * FROM v2_l1_briefs WHERE learnerId = :learnerId AND briefId = :briefId")
    protected abstract suspend fun findBrief(learnerId: String, briefId: String): V2L1BriefEntity?

    @Query("SELECT * FROM v2_discover_entries WHERE learnerId = :learnerId AND momentId = :momentId")
    protected abstract suspend fun findDiscover(learnerId: String, momentId: String): V2DiscoverEntryEntity?

    @Query("SELECT * FROM v2_notification_outbox WHERE learnerId = :learnerId AND interventionKey = :interventionKey")
    protected abstract suspend fun findNotificationOutbox(learnerId: String, interventionKey: String): V2NotificationOutboxEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertPackage(value: V2ContentPackageEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertMoment(value: V2LearningMomentEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertMomentRevision(value: V2LearningMomentRevisionEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertBrief(value: V2L1BriefEntity)

    @Update
    protected abstract suspend fun updateBrief(value: V2L1BriefEntity)

    @Update
    protected abstract suspend fun updateDiscover(value: V2DiscoverEntryEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertDiscover(value: V2DiscoverEntryEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertReceipt(value: V2PackageReceiptEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    protected abstract suspend fun insertNotificationOutbox(value: V2NotificationOutboxEntity)

    @Query("UPDATE v2_learning_moments SET currentRevisionId = :revisionId, state = :state WHERE learnerId = :learnerId AND momentId = :momentId")
    protected abstract suspend fun updateMomentCurrentRevision(
        learnerId: String,
        momentId: String,
        revisionId: String,
        state: String,
    )

    /**
     * The receipt and notification row are committed with content. A caller may
     * ACK the PC only after this method returns [V2PackagePersistState.PERSISTED]
     * or a payload-identical [V2PackagePersistState.ALREADY_PERSISTED].
     */
    @Transaction
    public open suspend fun persistAtomically(ingress: V2PackageIngress): V2PackagePersistState {
        val localAdmission = resolveAdmission(ingress)
        V2PackageAdmissionGate.validate(ingress, localAdmission)
        V2PackageIngressIntegrity.validate(ingress)
        val packageValue = ingress.packageEntity
        val previousPackage = findPackage(packageValue.learnerId, packageValue.packageId, packageValue.packageRevisionId)
        if (previousPackage != null) {
            require(previousPackage.payloadHash == packageValue.payloadHash) { "v2_package_revision_payload_conflict" }
            return V2PackagePersistState.ALREADY_PERSISTED
        }
        val moment = ingress.momentEntity
        val revision = ingress.momentRevisionEntity
        val previousMoment = findMoment(moment.learnerId, moment.momentId)
        if (previousMoment == null) {
            require(revision.revisionNumber == 1L && revision.replacesRevisionId == null) {
                "v2_initial_moment_revision_invalid"
            }
            insertMoment(moment)
        } else {
            require(
                previousMoment.episodeId == moment.episodeId &&
                    previousMoment.semanticLineageId == moment.semanticLineageId &&
                    previousMoment.learningAnchorId == moment.learningAnchorId &&
                    previousMoment.interventionKey == moment.interventionKey
            ) { "v2_moment_identity_conflict" }
            require(revision.replacesRevisionId == previousMoment.currentRevisionId) {
                "v2_moment_revision_predecessor_mismatch"
            }
            val predecessor = findMomentRevision(revision.learnerId, previousMoment.currentRevisionId)
                ?: throw IllegalStateException("v2_moment_current_revision_missing")
            require(predecessor.revisionNumber + 1L == revision.revisionNumber) {
                "v2_moment_revision_sequence_invalid"
            }
        }
        require(findMomentRevision(revision.learnerId, revision.momentRevisionId) == null) {
            "v2_moment_revision_already_persisted_without_package"
        }
        insertMomentRevision(revision)
        if (previousMoment != null) {
            updateMomentCurrentRevision(moment.learnerId, moment.momentId, revision.momentRevisionId, moment.state)
        }
        insertPackage(packageValue)
        val previousBrief = findBrief(ingress.briefEntity.learnerId, ingress.briefEntity.briefId)
        if (previousBrief == null) {
            insertBrief(ingress.briefEntity)
        } else {
            V2PackageIngressIntegrity.requireSameMomentBrief(previousBrief, ingress.briefEntity)
            require(previousBrief.interventionKey == ingress.briefEntity.interventionKey) { "v2_brief_intervention_conflict" }
            updateBrief(ingress.briefEntity)
        }
        val previousDiscover = findDiscover(ingress.discoverEntryEntity.learnerId, ingress.discoverEntryEntity.momentId)
        if (previousDiscover == null) {
            insertDiscover(ingress.discoverEntryEntity)
        } else {
            require(previousDiscover.briefId == ingress.discoverEntryEntity.briefId) { "v2_discover_brief_identity_conflict" }
            updateDiscover(ingress.discoverEntryEntity)
        }
        insertReceipt(createPersistenceReceipt(ingress, packageValue))
        val previousOutbox = findNotificationOutbox(
            packageValue.learnerId,
            moment.interventionKey,
        )
        if (previousOutbox == null) {
            insertNotificationOutbox(createNotificationOutbox(packageValue, moment, ingress.briefEntity))
        } else {
            require(
                previousOutbox.momentId == moment.momentId &&
                    previousOutbox.briefId == ingress.briefEntity.briefId
            ) { "v2_notification_outbox_identity_conflict" }
        }
        return V2PackagePersistState.PERSISTED
    }

    /** The transport may request persistence, but cannot author Android's ACK. */
    private fun createPersistenceReceipt(
        ingress: V2PackageIngress,
        packageValue: V2ContentPackageEntity,
    ): V2PackageReceiptEntity {
        val receiptId = "receipt-" + UUID.randomUUID()
        val idempotencyKey = listOf(
            "receipt", packageValue.learnerId, packageValue.packageId,
            packageValue.packageRevisionId, ingress.deliveryLeaseId,
        ).joinToString(":")
        val persistedElapsedNs = System.nanoTime()
        val transactionHash = sha256(
            listOf(
                receiptId, idempotencyKey, packageValue.learnerId, packageValue.sessionId,
                packageValue.captureConsentId, packageValue.consentGeneration.toString(),
                packageValue.processingEligibilityGrantId, packageValue.policyBundleHash,
                packageValue.protocolProfileId, packageValue.messageId, ingress.deliveryLeaseId,
                packageValue.packageId, packageValue.packageRevisionId, packageValue.payloadHash,
                persistedElapsedNs.toString(),
            ).joinToString("\n"),
        )
        return V2PackageReceiptEntity(
            learnerId = packageValue.learnerId,
            packageId = packageValue.packageId,
            packageRevisionId = packageValue.packageRevisionId,
            receiptMessageId = "receipt-message-" + UUID.randomUUID(),
            receiptId = receiptId,
            idempotencyKey = idempotencyKey,
            createdAt = Instant.now().toString(),
            sessionId = packageValue.sessionId,
            captureConsentId = packageValue.captureConsentId,
            consentGeneration = packageValue.consentGeneration,
            processingEligibilityGrantId = packageValue.processingEligibilityGrantId,
            policyBundleHash = packageValue.policyBundleHash,
            protocolProfileId = packageValue.protocolProfileId,
            deliveredMessageId = packageValue.messageId,
            deliveryLeaseId = ingress.deliveryLeaseId,
            packagePayloadHash = packageValue.payloadHash,
            transactionHash = transactionHash,
            persistedElapsedNs = persistedElapsedNs,
            disposition = "PERSISTED",
        )
    }

    /** Android owns notification state and timestamps; package ingress never does. */
    private fun createNotificationOutbox(
        packageValue: V2ContentPackageEntity,
        moment: V2LearningMomentEntity,
        brief: V2L1BriefEntity,
    ): V2NotificationOutboxEntity = V2NotificationOutboxEntity(
        learnerId = packageValue.learnerId,
        interventionKey = moment.interventionKey,
        briefId = brief.briefId,
        momentId = moment.momentId,
        packageRevisionId = packageValue.packageRevisionId,
        state = "PENDING_LOCAL_REVIEW",
        createdElapsedNs = System.nanoTime(),
    )

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString(separator = "") { byte -> "%02x".format(byte.toInt() and 0xff) }
}

@Database(
    entities = [
        V2ContentPackageEntity::class,
        V2LearningMomentEntity::class,
        V2LearningMomentRevisionEntity::class,
        V2L1BriefEntity::class,
        V2DiscoverEntryEntity::class,
        V2PackageReceiptEntity::class,
        V2NotificationOutboxEntity::class,
        V2AdmissionSessionEntity::class,
        V2AdmissionRouteEntity::class,
        V2AdmissionScopeEntity::class,
        V2AdmissionAudioEntity::class,
    ],
    version = 4,
    exportSchema = false,
)
public abstract class V2LearningPackageDatabase : RoomDatabase() {
    public abstract fun packageDao(): V2LearningPackageDao

    public companion object {
        private val MIGRATION_1_2: Migration = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN policyBundleHash TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN protocolProfileId TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN analysisRouteLeaseId TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN routeEpoch INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN audioSnapshotId TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN audioResolution TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN semanticAudioDecisionId TEXT")
            }
        }

        private val MIGRATION_2_3: Migration = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("CREATE TABLE IF NOT EXISTS v2_admission_sessions (learnerId TEXT NOT NULL, sessionId TEXT NOT NULL, captureConsentId TEXT NOT NULL, consentGeneration INTEGER NOT NULL, processingEligibilityGrantId TEXT NOT NULL DEFAULT '', policyBundleHash TEXT NOT NULL DEFAULT '', protocolProfileId TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL, PRIMARY KEY(learnerId, sessionId))")
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_v2_admission_sessions_learnerId_captureConsentId_consentGeneration ON v2_admission_sessions (learnerId, captureConsentId, consentGeneration)")
                db.execSQL("CREATE TABLE IF NOT EXISTS v2_admission_routes (learnerId TEXT NOT NULL, routeLeaseId TEXT NOT NULL, sessionId TEXT NOT NULL, consentGeneration INTEGER NOT NULL, routeEpoch INTEGER NOT NULL, state TEXT NOT NULL, PRIMARY KEY(learnerId, routeLeaseId))")
                db.execSQL("CREATE TABLE IF NOT EXISTS v2_admission_scopes (learnerId TEXT NOT NULL, scopeId TEXT NOT NULL, scopeHash TEXT NOT NULL, sessionId TEXT NOT NULL, consentGeneration INTEGER NOT NULL, stable INTEGER NOT NULL, l0ContinuityVerified INTEGER NOT NULL, runtimeRiskClear INTEGER NOT NULL, PRIMARY KEY(learnerId, scopeId, scopeHash))")
                db.execSQL("CREATE TABLE IF NOT EXISTS v2_admission_audio (learnerId TEXT NOT NULL, audioSnapshotId TEXT NOT NULL, sessionId TEXT NOT NULL, consentGeneration INTEGER NOT NULL, resolution TEXT NOT NULL, semanticAudioDecisionId TEXT, PRIMARY KEY(learnerId, audioSnapshotId))")
            }
        }

        private val MIGRATION_3_4: Migration = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE v2_content_packages ADD COLUMN processingEligibilityGrantId TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_admission_sessions ADD COLUMN processingEligibilityGrantId TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_admission_sessions ADD COLUMN policyBundleHash TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE v2_admission_sessions ADD COLUMN protocolProfileId TEXT NOT NULL DEFAULT ''")
                db.execSQL("CREATE TABLE IF NOT EXISTS v2_package_receipts_v4 (learnerId TEXT NOT NULL, packageId TEXT NOT NULL, packageRevisionId TEXT NOT NULL, receiptMessageId TEXT NOT NULL, receiptId TEXT NOT NULL, idempotencyKey TEXT NOT NULL, createdAt TEXT NOT NULL, sessionId TEXT NOT NULL, captureConsentId TEXT NOT NULL, consentGeneration INTEGER NOT NULL, processingEligibilityGrantId TEXT NOT NULL, policyBundleHash TEXT NOT NULL, protocolProfileId TEXT NOT NULL, deliveredMessageId TEXT NOT NULL, deliveryLeaseId TEXT NOT NULL, packagePayloadHash TEXT NOT NULL, transactionHash TEXT NOT NULL, persistedElapsedNs INTEGER NOT NULL, disposition TEXT NOT NULL, PRIMARY KEY(learnerId, packageId, packageRevisionId))")
                db.execSQL("INSERT INTO v2_package_receipts_v4 (learnerId, packageId, packageRevisionId, receiptMessageId, receiptId, idempotencyKey, createdAt, sessionId, captureConsentId, consentGeneration, processingEligibilityGrantId, policyBundleHash, protocolProfileId, deliveredMessageId, deliveryLeaseId, packagePayloadHash, transactionHash, persistedElapsedNs, disposition) SELECT learnerId, packageId, packageRevisionId, 'legacy-receipt-message:' || learnerId || ':' || packageId || ':' || packageRevisionId, 'legacy-receipt:' || learnerId || ':' || packageId || ':' || packageRevisionId, 'legacy-receipt:' || learnerId || ':' || packageId || ':' || packageRevisionId, '', '', '', 0, '', '', '', messageId, '', '', transactionHash, persistedElapsedNs, 'LEGACY_READ_ONLY' FROM v2_package_receipts")
                db.execSQL("DROP TABLE v2_package_receipts")
                db.execSQL("ALTER TABLE v2_package_receipts_v4 RENAME TO v2_package_receipts")
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_v2_package_receipts_receiptId ON v2_package_receipts (receiptId)")
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_v2_package_receipts_idempotencyKey ON v2_package_receipts (idempotencyKey)")
            }
        }

        public fun open(context: Context): V2LearningPackageDatabase = Room.databaseBuilder(
            context.applicationContext,
            V2LearningPackageDatabase::class.java,
            "zhixing_v2_learning_packages.db",
        ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4).build()
    }
}
