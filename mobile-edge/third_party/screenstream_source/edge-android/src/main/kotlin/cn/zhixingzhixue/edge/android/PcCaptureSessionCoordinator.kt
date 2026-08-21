package cn.zhixingzhixue.edge.android

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

public enum class PcCaptureMode {
    FULL_CONTINUOUS,
    SELECTED_APPS,
}

/**
 * Student-selected scope for one persistent MediaProjection session.
 *
 * It controls whether media may leave the device, not whether the capture
 * session itself remains alive.  A video or foreground-app switch never asks
 * the learner for a fresh capture consent.
 */
public data class PcCaptureModePolicy(
    val mode: PcCaptureMode,
    val selectedPackages: Set<String>,
) {
    init {
        require(selectedPackages.none { it.isBlank() }) { "capture_selected_package_blank" }
        require(mode != PcCaptureMode.FULL_CONTINUOUS || selectedPackages.isEmpty()) { "full_capture_disallows_selected_packages" }
        require(mode != PcCaptureMode.SELECTED_APPS || selectedPackages.isNotEmpty()) { "selected_apps_requires_packages" }
    }

    public fun allowsOutputFor(foregroundPackage: String?): Boolean =
        mode == PcCaptureMode.FULL_CONTINUOUS || foregroundPackage != null && foregroundPackage in selectedPackages

    /**
     * Applied before MediaProjection starts. Selected-app mode cannot expose
     * even its first encoded frame until a current local observation and the
     * paired-PC policy decision have both opened the gate.
     */
    public val initialPairedPcOutputAllowed: Boolean
        get() = mode == PcCaptureMode.FULL_CONTINUOUS

    public companion object {
        public fun fullContinuous(): PcCaptureModePolicy = PcCaptureModePolicy(PcCaptureMode.FULL_CONTINUOUS, emptySet())

        public fun selectedApps(packages: Set<String>): PcCaptureModePolicy =
            PcCaptureModePolicy(PcCaptureMode.SELECTED_APPS, packages.map { it.trim() }.toSet())
    }
}

/** Durable PC-consumer plan for an already user-authorized Android RTSP stream. */
public data class PcCapturePlan(
    val sessionId: String?,
    val rtspPort: Int,
    val rtspPath: String,
    val deviceId: String,
    val spkiSha256: String,
    val generation: Long,
    val desired: Boolean,
    val stopAcknowledged: Boolean,
    val pcState: String?,
    val error: String?,
    val capturePolicy: PcCaptureModePolicy = PcCaptureModePolicy.fullContinuous(),
    /** Local egress state; this is not a terminal CaptureSession state. */
    val captureOutputState: CaptureOutputGateTransition = CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS,
    val learnerId: String? = null,
    val captureConsentId: String? = null,
    val consentGeneration: Long? = null,
    val captureEpoch: Long? = null,
    val mediaRouteLeaseId: String? = null,
    val mediaRouteEpoch: Long? = null,
    val mediaCaptureEpoch: Long? = null,
)

/** The PC route carries the consent epoch; runner generations are independent. */
public fun isPcIssuedMediaRouteBound(consentCaptureEpoch: Long?, returnedCaptureEpoch: Long?): Boolean =
    consentCaptureEpoch != null && returnedCaptureEpoch != null && returnedCaptureEpoch > 0L &&
        consentCaptureEpoch == returnedCaptureEpoch

/**
 * Durable state boundary between the V5 screen (which alone asks for
 * MediaProjection) and the foreground service (which owns paired-PC recovery).
 */
public class PcCaptureSessionCoordinator(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val mutablePlan: MutableStateFlow<PcCapturePlan?> = MutableStateFlow(read())
    public val plan: StateFlow<PcCapturePlan?> = mutablePlan.asStateFlow()

    public fun begin(
        rtspPort: Int,
        rtspPath: String,
        deviceId: String,
        spkiSha256: String,
        capturePolicy: PcCaptureModePolicy = PcCaptureModePolicy.fullContinuous(),
        consent: PcCaptureConsentSnapshot,
    ) {
        require(rtspPort in 1..65535) { "capture_rtsp_port_invalid" }
        require(rtspPath.matches(PATH_PATTERN)) { "capture_rtsp_path_invalid" }
        require(deviceId.isNotBlank()) { "pc_delivery_device_id_required" }
        require(spkiSha256.isNotBlank()) { "pc_delivery_spki_required" }
        val previous = mutablePlan.value
        if (
            previous?.desired == true &&
            previous.sessionId != null &&
            previous.rtspPort == rtspPort && previous.rtspPath == rtspPath &&
            previous.deviceId == deviceId && previous.spkiSha256 == spkiSha256 && previous.capturePolicy == capturePolicy &&
            previous.pcState in ACTIVE_STATES
        ) return
        write(
            PcCapturePlan(
                sessionId = null,
                rtspPort = rtspPort,
                rtspPath = rtspPath,
                deviceId = deviceId,
                spkiSha256 = spkiSha256,
                generation = (previous?.generation ?: 0L) + 1L,
                desired = true,
                stopAcknowledged = false,
                pcState = "STARTING",
                error = null,
                capturePolicy = capturePolicy,
                captureOutputState = if (capturePolicy.mode == PcCaptureMode.SELECTED_APPS) {
                    CaptureOutputGateTransition.BLOCKED_UNOBSERVED
                } else {
                    CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS
                },
                learnerId = consent.learnerId,
                captureConsentId = consent.captureConsentId,
                consentGeneration = consent.consentGeneration,
                captureEpoch = consent.captureEpoch,
            ),
        )
    }

    /** Persist the id before the POST so a lost HTTP response stays idempotent. */
    public fun prepareStart(generation: Long): PcCapturePlan? {
        val current = mutablePlan.value ?: return null
        if (!current.desired || current.generation != generation) return null
        if (current.sessionId != null) return current
        val prepared = current.copy(sessionId = "phone-" + UUID.randomUUID(), pcState = "STARTING", error = null)
        write(prepared)
        return prepared
    }

    public fun report(generation: Long, state: String, error: String?) {
        val current = mutablePlan.value ?: return
        if (current.generation == generation) write(current.copy(pcState = state, error = error))
    }

    /** A route is accepted only if this same capture generation received it from the paired PC. */
    public fun bindPcIssuedMediaRoute(
        generation: Long,
        leaseId: String?,
        routeEpoch: Long?,
        captureEpoch: Long?,
    ) {
        val current = mutablePlan.value ?: return
        if (
            current.generation != generation || leaseId.isNullOrBlank() || routeEpoch == null || routeEpoch < 1L ||
            !isPcIssuedMediaRouteBound(current.captureEpoch, captureEpoch)
        ) return
        write(current.copy(mediaRouteLeaseId = leaseId, mediaRouteEpoch = routeEpoch, mediaCaptureEpoch = captureEpoch))
    }

    /** Egress filtering is observable, but never changes desired/authorization. */
    public fun reportCaptureOutput(generation: Long, outputState: CaptureOutputGateTransition) {
        val current = mutablePlan.value ?: return
        if (current.generation == generation && current.captureOutputState != outputState) {
            write(current.copy(captureOutputState = outputState))
        }
    }

    /** PC restart: retain authorized source configuration, discard only stale worker id. */
    public fun restart(generation: Long) {
        val current = mutablePlan.value ?: return
        if (current.desired && current.generation == generation) {
            write(current.copy(sessionId = null, generation = current.generation + 1L, pcState = "STARTING", error = null))
        }
    }

    public fun requestStop() {
        val current = mutablePlan.value ?: return
        write(current.copy(desired = false, stopAcknowledged = false, pcState = "STOPPING", error = null))
    }

    public fun acknowledgeStop(generation: Long, state: String, error: String?) {
        val current = mutablePlan.value ?: return
        if (current.generation == generation && !current.desired) {
            write(current.copy(stopAcknowledged = true, pcState = state, error = error))
        }
    }

    public fun clear(generation: Long? = null) {
        val current = mutablePlan.value
        if (generation == null || current?.generation == generation) {
            preferences.edit().clear().commit()
            mutablePlan.value = null
        }
    }

    private fun write(value: PcCapturePlan) {
        preferences.edit()
            .putString(KEY_SESSION_ID, value.sessionId)
            .putInt(KEY_RTSP_PORT, value.rtspPort)
            .putString(KEY_RTSP_PATH, value.rtspPath)
            .putString(KEY_DEVICE_ID, value.deviceId)
            .putString(KEY_SPKI, value.spkiSha256)
            .putLong(KEY_GENERATION, value.generation)
            .putBoolean(KEY_DESIRED, value.desired)
            .putBoolean(KEY_STOP_ACKNOWLEDGED, value.stopAcknowledged)
            .putString(KEY_PC_STATE, value.pcState)
            .putString(KEY_ERROR, value.error)
            .putString(KEY_CAPTURE_MODE, value.capturePolicy.mode.name)
            .putStringSet(KEY_SELECTED_PACKAGES, value.capturePolicy.selectedPackages)
            .putString(KEY_CAPTURE_OUTPUT_STATE, value.captureOutputState.name)
            .putString(KEY_LEARNER_ID, value.learnerId)
            .putString(KEY_CAPTURE_CONSENT_ID, value.captureConsentId)
            .putLong(KEY_CONSENT_GENERATION, value.consentGeneration ?: 0L)
            .putLong(KEY_CAPTURE_EPOCH, value.captureEpoch ?: 0L)
            .putString(KEY_MEDIA_ROUTE_LEASE_ID, value.mediaRouteLeaseId)
            .putLong(KEY_MEDIA_ROUTE_EPOCH, value.mediaRouteEpoch ?: 0L)
            .putLong(KEY_MEDIA_CAPTURE_EPOCH, value.mediaCaptureEpoch ?: 0L)
            .commit()
        mutablePlan.value = value
    }

    private fun read(): PcCapturePlan? {
        val sessionId = preferences.getString(KEY_SESSION_ID, null)?.takeIf { it.isNotBlank() }
        val desired = preferences.getBoolean(KEY_DESIRED, false)
        if (!desired && sessionId == null) return null
        val port = preferences.getInt(KEY_RTSP_PORT, -1)
        val path = preferences.getString(KEY_RTSP_PATH, null)
        val deviceId = preferences.getString(KEY_DEVICE_ID, null)
        val spki = preferences.getString(KEY_SPKI, null)
        if (port !in 1..65535 || path.isNullOrBlank() || !path.matches(PATH_PATTERN) || deviceId.isNullOrBlank() || spki.isNullOrBlank()) return null
        val capturePolicy = runCatching {
            val mode = preferences.getString(KEY_CAPTURE_MODE, PcCaptureMode.FULL_CONTINUOUS.name)
                ?.let(PcCaptureMode::valueOf) ?: PcCaptureMode.FULL_CONTINUOUS
            PcCaptureModePolicy(mode, preferences.getStringSet(KEY_SELECTED_PACKAGES, emptySet()) ?: emptySet())
        }.getOrNull() ?: return null
        val outputState = preferences.getString(KEY_CAPTURE_OUTPUT_STATE, null)
            ?.let { raw -> runCatching { CaptureOutputGateTransition.valueOf(raw) }.getOrNull() }
            ?: if (capturePolicy.mode == PcCaptureMode.SELECTED_APPS) {
                CaptureOutputGateTransition.BLOCKED_UNOBSERVED
            } else {
                CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS
            }
        return PcCapturePlan(
            sessionId = sessionId,
            rtspPort = port,
            rtspPath = path,
            deviceId = deviceId,
            spkiSha256 = spki,
            generation = preferences.getLong(KEY_GENERATION, 0L).coerceAtLeast(1L),
            desired = desired,
            stopAcknowledged = preferences.getBoolean(KEY_STOP_ACKNOWLEDGED, false),
            pcState = preferences.getString(KEY_PC_STATE, null),
            error = preferences.getString(KEY_ERROR, null),
            capturePolicy = capturePolicy,
            captureOutputState = outputState,
            mediaRouteLeaseId = preferences.getString(KEY_MEDIA_ROUTE_LEASE_ID, null)?.takeIf { it.isNotBlank() },
            mediaRouteEpoch = preferences.getLong(KEY_MEDIA_ROUTE_EPOCH, 0L).takeIf { it > 0L },
            mediaCaptureEpoch = preferences.getLong(KEY_MEDIA_CAPTURE_EPOCH, 0L).takeIf { it > 0L },
            learnerId = preferences.getString(KEY_LEARNER_ID, null)?.takeIf { it.isNotBlank() },
            captureConsentId = preferences.getString(KEY_CAPTURE_CONSENT_ID, null)?.takeIf { it.isNotBlank() },
            consentGeneration = preferences.getLong(KEY_CONSENT_GENERATION, 0L).takeIf { it > 0L },
            captureEpoch = preferences.getLong(KEY_CAPTURE_EPOCH, 0L).takeIf { it > 0L },
        )
    }

    private companion object {
        private val PATH_PATTERN: Regex = Regex("[A-Za-z0-9._~-]+")
        private val ACTIVE_STATES: Set<String> = setOf("STARTING", "RUNNING", "STOPPING")
        private const val PREFERENCES: String = "zhixing_pc_capture_plan"
        private const val KEY_SESSION_ID: String = "session_id"
        private const val KEY_RTSP_PORT: String = "rtsp_port"
        private const val KEY_RTSP_PATH: String = "rtsp_path"
        private const val KEY_DEVICE_ID: String = "device_id"
        private const val KEY_SPKI: String = "spki"
        private const val KEY_GENERATION: String = "generation"
        private const val KEY_DESIRED: String = "desired"
        private const val KEY_STOP_ACKNOWLEDGED: String = "stop_acknowledged"
        private const val KEY_PC_STATE: String = "pc_state"
        private const val KEY_ERROR: String = "error"
        private const val KEY_CAPTURE_MODE: String = "capture_mode"
        private const val KEY_SELECTED_PACKAGES: String = "selected_packages"
        private const val KEY_CAPTURE_OUTPUT_STATE: String = "capture_output_state"
        private const val KEY_MEDIA_ROUTE_LEASE_ID: String = "media_route_lease_id"
        private const val KEY_MEDIA_ROUTE_EPOCH: String = "media_route_epoch"
        private const val KEY_MEDIA_CAPTURE_EPOCH: String = "media_capture_epoch"
        private const val KEY_LEARNER_ID: String = "learner_id"
        private const val KEY_CAPTURE_CONSENT_ID: String = "capture_consent_id"
        private const val KEY_CONSENT_GENERATION: String = "consent_generation"
        private const val KEY_CAPTURE_EPOCH: String = "capture_epoch"
    }
}
