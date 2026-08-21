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
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import info.dvkr.screenstream.rtsp.RtspTransportFacade
import info.dvkr.screenstream.rtsp.RtspTransportStatus
import org.koin.core.context.GlobalContext
import org.koin.core.component.get

/**
 * Student-enabled foreground dataSync service.  It owns the paired-PC polling
 * lifecycle, so delivery continues while the learner is reading or watching in
 * another app.  It is not a hidden background collector and can be stopped by
 * unpairing or Android's normal foreground-service controls.
 */
public class PcSyncForegroundService : Service() {
    private val serviceScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var syncJob: Job? = null
    private var captureJob: Job? = null
    private var syncFrameJob: Job? = null
    private var audioCapabilityJob: Job? = null
    private var accessibilityObservationJob: Job? = null
    private var usageStatsObservationJob: Job? = null
    private var latestForegroundObservation: ForegroundAppObservation? = null
    private var lastForegroundReportKey: String? = null
    private var lastAudioCapabilitySnapshotId: String? = null
    private var v2MediaEgress: PcV2MediaEgressController? = null
    private var v2MediaEgressKey: String? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android starts the foreground-service deadline before delivering this
        // command.  MobileAppServices.initialize() constructs several local
        // stores, so it must never run ahead of the foreground notification.
        // Even a stop/no-link command is promoted first, then immediately
        // stops below; that is safer than risking an OS process kill.
        promoteToForeground()
        val link = MobileAppServices.pcLinkStore(this).read()
        val captureCoordinator = MobileAppServices.pcCaptureSessionCoordinator(this)
        val userIntentStore = MobileAppServices.pcSyncUserIntentStore(this)
        if (intent?.action == ACTION_STOP) {
            userIntentStore.recordLearnerStop()
            captureCoordinator.requestStop()
            setTransportOutputAllowed(false)
            stopV2MediaEgress()
            stopAuthorizedUserCapture()
            stopSelf()
            return START_NOT_STICKY
        }
        if (link == null) {
            // The link removal may race this service's START_STICKY restart.
            // A missing credential is never permission to keep capture alive.
            userIntentStore.recordLearnerStop()
            captureCoordinator.requestStop()
            setTransportOutputAllowed(false)
            stopV2MediaEgress()
            stopAuthorizedUserCapture()
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_CAPTURE_STARTED) userIntentStore.recordExplicitStart()
        if (!userIntentStore.read(hasPairedPc = true).permitsServiceStart(hasPairedPc = true)) {
            // A null START_STICKY intent, process restore, or DHCP reconnect
            // must not override a learner's earlier stop decision.
            captureCoordinator.requestStop()
            setTransportOutputAllowed(false)
            stopV2MediaEgress()
            stopAuthorizedUserCapture()
            stopSelf()
            return START_NOT_STICKY
        }
        when (intent?.action) {
            ACTION_CAPTURE_STARTED -> link.let { pairedLink ->
                val capturePolicy = capturePolicyFromIntent(intent) ?: run {
                    Log.e(TAG, "Refusing capture start with an invalid selected-app policy")
                    captureCoordinator.requestStop()
                    return@let
                }
                val existing = captureCoordinator.plan.value
                val consent = if (
                    existing?.desired == true &&
                    existing.learnerId != null &&
                    existing.captureConsentId != null &&
                    existing.consentGeneration != null &&
                    existing.captureEpoch != null
                ) {
                    PcCaptureConsentSnapshot(
                        existing.learnerId,
                        existing.captureConsentId,
                        existing.consentGeneration,
                        existing.captureEpoch,
                    )
                } else {
                    MobileAppServices.pcCaptureConsentStore(this).beginExplicitCapture()
                }
                captureCoordinator.begin(
                    intent.getIntExtra(EXTRA_RTSP_PORT, -1),
                    intent.getStringExtra(EXTRA_RTSP_PATH).orEmpty(),
                    pairedLink.deviceId,
                    pairedLink.spkiSha256,
                    capturePolicy = capturePolicy,
                    consent = consent,
                )
            }
            ACTION_CAPTURE_STOPPED -> {
                // Stop the v2 producer at the same local user-stop boundary;
                // do not let an in-memory HTTPS queue keep uploading stale
                // frames while the PC is settling the interruption record.
                captureCoordinator.requestStop()
                setTransportOutputAllowed(false)
                stopV2MediaEgress()
            }
        }
        resetSelectedAppOutputGate(captureCoordinator)
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
                        val error = result.exceptionOrNull()
                        if (PcSyncServiceFaultPolicy.requiresLearnerStop(error?.message)) {
                            stopForCredentialRevocation()
                            return@launch
                        }
                        Log.w(TAG, "Paired-PC synchronization failed; retrying with backoff", error)
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
        ensureCaptureJob()
        ensureSyncFrameJob()
        ensureAudioCapabilityJob()
        ensureForegroundObservationJobs()
        return START_STICKY
    }

    /**
     * A service/process restart has lost the freshness of foreground evidence.
     * Selected-app mode therefore closes egress until it receives a new device
     * observation; the MediaProjection session itself remains untouched.
     */
    private fun resetSelectedAppOutputGate(coordinator: PcCaptureSessionCoordinator) {
        val plan = coordinator.plan.value ?: return
        if (!plan.desired) return
        if (plan.capturePolicy.mode == PcCaptureMode.SELECTED_APPS) {
            latestForegroundObservation = null
            lastForegroundReportKey = null
            coordinator.reportCaptureOutput(plan.generation, CaptureOutputGateTransition.BLOCKED_UNOBSERVED)
            setTransportOutputAllowed(false)
        } else {
            coordinator.reportCaptureOutput(plan.generation, CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS)
            setTransportOutputAllowed(true)
        }
    }

    private fun ensureForegroundObservationJobs() {
        if (accessibilityObservationJob?.isActive != true) {
            accessibilityObservationJob = serviceScope.launch {
                ForegroundAppObservationBus.observations.collect { observation ->
                    latestForegroundObservation = observation
                    applyForegroundObservation(observation)
                }
            }
        }
        if (usageStatsObservationJob?.isActive != true) {
            usageStatsObservationJob = serviceScope.launch {
                val observer = UsageStatsForegroundAppObserver(this@PcSyncForegroundService)
                while (isActive) {
                    val packageName = observer.mostRecentForegroundPackage(System.currentTimeMillis() - USAGE_STATS_LOOKBACK_MS)
                    if (packageName != null) {
                        val observation = ForegroundAppObservation(
                            packageName,
                            ForegroundAppObservationSource.USAGE_STATS,
                            SystemClock.elapsedRealtime(),
                        )
                        latestForegroundObservation = observation
                        applyForegroundObservation(observation)
                    }
                    delay(FOREGROUND_OBSERVATION_POLL_MS)
                }
            }
        }
    }

    private suspend fun applyForegroundObservation(observation: ForegroundAppObservation?) {
        val coordinator = MobileAppServices.pcCaptureSessionCoordinator(this)
        val plan = coordinator.plan.value ?: return
        if (!plan.desired) return
        if (plan.capturePolicy.mode == PcCaptureMode.FULL_CONTINUOUS) {
            coordinator.reportCaptureOutput(plan.generation, CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS)
            setTransportOutputAllowed(true)
            return
        }
        if (observation == null) {
            coordinator.reportCaptureOutput(plan.generation, CaptureOutputGateTransition.BLOCKED_UNOBSERVED)
            setTransportOutputAllowed(false)
            return
        }
        val localGate = ForegroundAppOutputGate(plan.capturePolicy).observe(observation.packageName, observation.source)
        val sessionId = plan.sessionId
        if (sessionId.isNullOrBlank()) {
            // The PC has not created the auditable CaptureSession yet. Keep
            // egress closed even if Android has already seen a selected app.
            coordinator.reportCaptureOutput(plan.generation, CaptureOutputGateTransition.BLOCKED_POLICY_UNCONFIRMED)
            setTransportOutputAllowed(false)
            return
        }
        val reportKey = "${plan.generation}:${sessionId}:${observation.source}:${observation.packageName}"
        if (reportKey == lastForegroundReportKey) {
            setTransportOutputAllowed(
                localGate.isOutputAllowed &&
                    plan.captureOutputState == CaptureOutputGateTransition.ALLOWED_SELECTED_APP,
            )
            return
        }
        val decisionResult = runCatching {
            MobileAppServices.pcDeliveryClient(this).reportForegroundApp(sessionId, observation.packageName, observation.source)
        }
        if (PcSyncServiceFaultPolicy.requiresLearnerStop(decisionResult.exceptionOrNull()?.message)) {
            stopForCredentialRevocation()
            return
        }
        val decision = decisionResult.getOrNull()
        // A gateway still starting/recovering must be retried; only a real
        // policy response is safe to deduplicate.
        lastForegroundReportKey = reportKey.takeIf { decision != null }
        val pcAllowsOutput = decision?.outputState == "STREAMING_ALLOWED"
        val outputAllowed = localGate.isOutputAllowed && pcAllowsOutput
        val state = when {
            outputAllowed -> localGate.transition
            decision == null -> CaptureOutputGateTransition.BLOCKED_POLICY_UNCONFIRMED
            else -> localGate.transition
        }
        coordinator.reportCaptureOutput(plan.generation, state)
        setTransportOutputAllowed(outputAllowed)
    }

    private fun setTransportOutputAllowed(allowed: Boolean) {
        val selectedAppMode = MobileAppServices.pcCaptureSessionCoordinator(this).plan.value
            ?.capturePolicy?.mode == PcCaptureMode.SELECTED_APPS
        v2MediaEgress?.setOutputAllowed(
            allowed,
            leaseDurationMs = if (allowed && selectedAppMode) FOREGROUND_OUTPUT_LEASE_MS else null,
        )
        runCatching { GlobalContext.get().get<RtspTransportFacade>() }
            .onSuccess { facade -> facade.setPairedPcOutputAllowed(allowed) }
            .onFailure { error -> Log.w(TAG, "RTSP output gate unavailable", error) }
    }

    private fun capturePolicyFromIntent(intent: Intent): PcCaptureModePolicy? = runCatching {
        val mode = intent.getStringExtra(EXTRA_CAPTURE_MODE)
            ?.let(PcCaptureMode::valueOf) ?: PcCaptureMode.FULL_CONTINUOUS
        val selectedPackages = intent.getStringArrayListExtra(EXTRA_SELECTED_PACKAGES)?.toSet() ?: emptySet()
        PcCaptureModePolicy(mode, selectedPackages)
    }.getOrNull()

    /**
     * Keeps a bounded IDR cadence only while this foreground service has a
     * confirmed paired-PC consumer for an already user-authorized capture.
     * It never starts projection, creates an RTSP client, or changes capture
     * settings.  Short independently decodable fragments keep the PC's
     * OCR/ASR/VLM lanes aligned to the same media window.
     */
    private fun ensureSyncFrameJob() {
        if (syncFrameJob?.isActive == true) return
        syncFrameJob = serviceScope.launch {
            val facade = runCatching { GlobalContext.get().get<RtspTransportFacade>() }
                .getOrElse { error ->
                    Log.w(TAG, "RTSP transport unavailable for keyframe cadence", error)
                    return@launch
                }
            val coordinator = MobileAppServices.pcCaptureSessionCoordinator(this@PcSyncForegroundService)
            while (isActive) {
                val plan = coordinator.plan.value
                val transport = facade.state.value
                val hasConfirmedPcConsumer =
                    plan?.desired == true &&
                        !plan.sessionId.isNullOrBlank() &&
                        plan.pcState == "RUNNING" &&
                        transport.status == RtspTransportStatus.STREAMING &&
                        transport.activeConsumerCount > 0
                if (hasConfirmedPcConsumer) {
                    facade.requestSyncFrame()
                    delay(SYNC_FRAME_INTERVAL_MS)
                } else {
                    delay(SYNC_FRAME_IDLE_RECHECK_MS)
                }
            }
        }
    }

    /**
     * Ships only technical audio capability and raw timing facts to the
     * already paired PC. It never opens MediaProjection, turns on a microphone,
     * or turns encoder state into a verified same-source audio claim.
     */
    private fun ensureAudioCapabilityJob() {
        if (audioCapabilityJob?.isActive == true) return
        audioCapabilityJob = serviceScope.launch {
            val facade = runCatching { GlobalContext.get().get<RtspTransportFacade>() }
                .getOrElse { error ->
                    Log.w(TAG, "RTSP transport unavailable for audio capability telemetry", error)
                    return@launch
                }
            val client = MobileAppServices.pcDeliveryClient(this@PcSyncForegroundService)
            val coordinator = MobileAppServices.pcCaptureSessionCoordinator(this@PcSyncForegroundService)
            while (isActive) {
                val plan = coordinator.plan.value
                val sessionId = plan?.takeIf { it.desired }?.sessionId
                if (plan == null || sessionId.isNullOrBlank()) {
                    lastAudioCapabilitySnapshotId = null
                    delay(AUDIO_CAPABILITY_REPORT_INTERVAL_MS)
                    continue
                }
                val transport = facade.state.value
                if (transport.status !in ACTIVE_RTSP_STATES) {
                    delay(AUDIO_CAPABILITY_REPORT_INTERVAL_MS)
                    continue
                }
                val report = PcAudioCapabilityReport.fromTransport(
                    sessionId = sessionId,
                    captureGeneration = plan.generation,
                    applicationPackageId = latestForegroundObservation?.packageName,
                    transport = transport.copy(timing = facade.currentTimingSnapshot()),
                )
                if (report != null && report.snapshotId != lastAudioCapabilitySnapshotId) {
                    val reportResult = runCatching { client.reportAudioCapability(sessionId, report) }
                    if (PcSyncServiceFaultPolicy.requiresLearnerStop(reportResult.exceptionOrNull()?.message)) {
                        stopForCredentialRevocation()
                        return@launch
                    }
                    reportResult
                        .onSuccess { receipt ->
                            // Only the paired-PC receipt lets us coalesce a retry.
                            // A failed POST keeps the same stable snapshot id.
                            lastAudioCapabilitySnapshotId = receipt.snapshotId
                        }
                        .onFailure { error -> Log.w(TAG, "PC audio capability report unavailable", error) }
                }
                delay(AUDIO_CAPABILITY_REPORT_INTERVAL_MS)
            }
        }
    }

    /**
     * Owns PC-worker recovery independently of the Compose route.  It does
     * not open MediaProjection or invent an RTSP source; it only consumes a
     * plan written after the real RTSP service reported STREAMING.
     */
    private fun ensureCaptureJob() {
        if (captureJob?.isActive == true) return
        captureJob = serviceScope.launch {
            val client = MobileAppServices.pcDeliveryClient(this@PcSyncForegroundService)
            val coordinator = MobileAppServices.pcCaptureSessionCoordinator(this@PcSyncForegroundService)
            var retryDelayMs = INITIAL_RETRY_DELAY_MS
            // This permit exists only in this live foreground-service process.
            // It is granted after this service itself observes the gateway lose
            // an already-running session.  It is deliberately not persisted:
            // after an app/service restart, a retained STREAMING label alone
            // is still insufficient proof of an authorized projection.
            var restartRecoveryGeneration: Long? = null
            var restartRecoveryExpiresAtNs: Long = 0L
            while (isActive) {
                val plan = coordinator.plan.value ?: return@launch
                // A PC session id becomes durable asynchronously. Re-apply the
                // latest observation at that point so a selected app can resume
                // output without a new MediaProjection permission prompt.
                applyForegroundObservation(latestForegroundObservation)
                val link = MobileAppServices.pcLinkStore(this@PcSyncForegroundService).read()
                if (link == null || link.deviceId != plan.deviceId || link.spkiSha256 != plan.spkiSha256) {
                    coordinator.clear(plan.generation)
                    return@launch
                }
                if (!plan.desired) {
                    val sessionId = plan.sessionId
                    if (sessionId == null) {
                        coordinator.clear(plan.generation)
                        return@launch
                    }
                    if (!plan.stopAcknowledged) {
                        runCatching { client.stopCaptureSession(sessionId) }
                            .onSuccess { session ->
                                if (isTerminal(session.state)) coordinator.clear(plan.generation)
                                else coordinator.acknowledgeStop(plan.generation, session.state, session.error)
                                retryDelayMs = INITIAL_RETRY_DELAY_MS
                            }
                            .onFailure { error ->
                                if (PcSyncServiceFaultPolicy.requiresLearnerStop(error.message)) {
                                    stopForCredentialRevocation()
                                    return@launch
                                }
                                if (error.message == "pc_delivery_http_404") {
                                    // The user has already stopped the Android source.  A
                                    // lost PC worker must not be recreated during tail-window
                                    // settlement, and must not be reported as completed.  The
                                    // durable PC evidence/outbox audit remains on the gateway;
                                    // remove only this obsolete local control plan so the
                                    // connection page does not present a past 404 as a current
                                    // capture failure.
                                    coordinator.clear(plan.generation)
                                    return@launch
                                }
                                coordinator.report(plan.generation, "STOPPING", error.message?.take(160) ?: "pc_capture_stop_unavailable")
                                delay(retryDelayMs)
                                retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                            }
                    } else {
                        runCatching { client.captureSessionStatus(sessionId) }
                            .onSuccess { session ->
                                if (isTerminal(session.state)) coordinator.clear(plan.generation)
                                else coordinator.report(plan.generation, session.state, session.error)
                                retryDelayMs = INITIAL_RETRY_DELAY_MS
                            }
                            .onFailure { error ->
                                if (PcSyncServiceFaultPolicy.requiresLearnerStop(error.message)) {
                                    stopForCredentialRevocation()
                                    return@launch
                                }
                                if (error.message == "pc_delivery_http_404") {
                                    coordinator.clear(plan.generation)
                                    return@launch
                                }
                                coordinator.report(plan.generation, "STOPPING", error.message?.take(160) ?: "pc_capture_settlement_unavailable")
                                delay(retryDelayMs)
                                retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                            }
                    }
                    delay(CAPTURE_STATUS_INTERVAL_MS)
                    continue
                }
                val transportResult = runCatching {
                    GlobalContext.get().get<RtspTransportFacade>().state.value
                }
                if (transportResult.isFailure) {
                    val error = transportResult.exceptionOrNull()
                    // A persisted plan is proof that the UI once observed STREAMING,
                    // not proof that the RTSP dependency is available now.  Fail
                    // closed here: never create a PC worker without re-reading it.
                    coordinator.report(plan.generation, "RECOVERING", error?.message?.take(160) ?: "rtsp_transport_unavailable")
                    delay(retryDelayMs)
                    retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                    continue
                }
                val transport = transportResult.getOrThrow()
                if (transport.status !in ACTIVE_RTSP_STATES) {
                    coordinator.requestStop()
                    continue
                }
                // A stale RTSP service can retain a PLAY/STREAMING state after
                // Android has revoked MediaProjection.  A PC worker is allowed
                // only after the handset's encoder has emitted a *recent*
                // video or audio timestamp; the status label alone is not
                // proof that there is an authorized source to consume.
                val lastMediaEmitNs = transport.timing?.lastMediaEmitElapsedRealtimeNs
                val nowNs = SystemClock.elapsedRealtimeNanos()
                val hasRecentAuthorizedMedia = lastMediaEmitNs != null && nowNs - lastMediaEmitNs in 0..MAX_MEDIA_EMIT_AGE_NS
                val mayRecoverNoConsumer =
                    restartRecoveryGeneration == plan.generation &&
                        nowNs <= restartRecoveryExpiresAtNs &&
                        transport.status == RtspTransportStatus.STREAMING_NO_CONSUMER
                if (!hasRecentAuthorizedMedia && !mayRecoverNoConsumer) {
                    // A listener socket is not evidence of a live projection.
                    // If the PC runner has already terminated while this stale
                    // Android RTSP server remains bound, polling only the local
                    // facade leaves port 8554 open forever and every PC retry
                    // receives an invalid source.  Ask the owning PC session
                    // before waiting again; a terminal result must actively
                    // close the user-authorized capture and its stale listener.
                    val staleSessionId = plan.sessionId
                    if (staleSessionId != null) {
                        runCatching { client.captureSessionStatus(staleSessionId) }
                            .onSuccess { session ->
                                coordinator.report(plan.generation, session.state, session.error)
                                if (session.state.startsWith("FAILED") || session.state in TERMINAL_CAPTURE_STATES) {
                                    coordinator.requestStop()
                                    stopAuthorizedUserCapture()
                                }
                            }
                            .onFailure { error ->
                                if (PcSyncServiceFaultPolicy.requiresLearnerStop(error.message)) {
                                    stopForCredentialRevocation()
                                    return@launch
                                } else if (PcSyncServiceFaultPolicy.requiresGatewayCaptureRecovery(error.message)) {
                                    // The PC gateway may have restarted after the handset had
                                    // temporarily stopped v2 egress.  Its volatile supervisor
                                    // state is gone, but MediaProjection consent remains valid;
                                    // rebuild only the PC consumer and retain that consent.
                                    stopV2MediaEgress()
                                    coordinator.report(plan.generation, "RECOVERING", "pc_gateway_restarted_settling_previous_tail")
                                    delay(GATEWAY_RESTART_SETTLEMENT_DELAY_MS)
                                    val latest = coordinator.plan.value
                                    if (
                                        latest?.desired == true &&
                                        latest.generation == plan.generation &&
                                        latest.sessionId == staleSessionId
                                    ) {
                                        coordinator.restart(plan.generation)
                                        coordinator.plan.value?.takeIf { it.desired }?.let { replacement ->
                                            restartRecoveryGeneration = replacement.generation
                                            restartRecoveryExpiresAtNs = SystemClock.elapsedRealtimeNanos() + RECOVERY_NO_CONSUMER_PERMIT_NS
                                        }
                                    }
                                } else {
                                    coordinator.report(
                                        plan.generation,
                                        "RECOVERING",
                                        error.message?.take(160) ?: "pc_capture_stale_media_status_unavailable",
                                    )
                                }
                            }
                    } else {
                        coordinator.report(plan.generation, "RECOVERING", "awaiting_recent_authorized_media")
                    }
                    delay(CAPTURE_STATUS_INTERVAL_MS)
                    continue
                }
                val prepared = coordinator.prepareStart(plan.generation)
                if (prepared != null && plan.sessionId == null) {
                    runCatching {
                        client.startCaptureSession(
                            prepared.sessionId!!,
                            prepared.generation,
                            prepared.rtspPort,
                            prepared.rtspPath,
                            prepared.capturePolicy,
                            consent = prepared.learnerId?.let { learnerId ->
                                PcCaptureConsentSnapshot(
                                    learnerId = learnerId,
                                    captureConsentId = prepared.captureConsentId ?: return@let null,
                                    consentGeneration = prepared.consentGeneration ?: return@let null,
                                    captureEpoch = prepared.captureEpoch ?: return@let null,
                                )
                            },
                        )
                    }.onSuccess { session ->
                        coordinator.report(prepared.generation, session.state, session.error)
                        coordinator.bindPcIssuedMediaRoute(
                            prepared.generation,
                            session.mediaRouteLeaseId,
                            session.mediaRouteEpoch,
                            session.captureEpoch,
                        )
                        installV2MediaEgress(coordinator, session)
                        restartRecoveryGeneration = null
                        restartRecoveryExpiresAtNs = 0L
                        retryDelayMs = INITIAL_RETRY_DELAY_MS
                    }.onFailure { error ->
                        if (PcSyncServiceFaultPolicy.requiresLearnerStop(error.message)) {
                            stopForCredentialRevocation()
                            return@launch
                        }
                        coordinator.report(prepared.generation, "RECOVERING", error.message?.take(160) ?: "pc_capture_start_failed")
                        runCatching { client.reconnectFromNearbyGateway() }
                        delay(retryDelayMs)
                        retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                    }
                    continue
                }
                // prepareStart() persists the generated id before the POST.  Read
                // again rather than using the pre-POST plan so each generation can
                // poll only its own durable worker id.
                val activePlan = coordinator.plan.value
                val activeSessionId = activePlan?.takeIf {
                    it.desired && it.generation == plan.generation
                }?.sessionId
                if (activeSessionId == null) {
                    delay(CAPTURE_STATUS_INTERVAL_MS)
                    continue
                }
                runCatching { client.captureSessionStatus(activeSessionId) }
                    .onSuccess { session ->
                        coordinator.report(plan.generation, session.state, session.error)
                        installV2MediaEgress(coordinator, session)
                        when {
                            session.state.startsWith("FAILED") -> {
                                coordinator.requestStop()
                                stopAuthorizedUserCapture()
                            }
                            session.state in TERMINAL_CAPTURE_STATES -> {
                                // A completed worker while the persisted plan
                                // is still desired means the PC lost its live
                                // consumer; recreate it instead of leaving
                            // MediaProjection with no receiver.
                            coordinator.restart(plan.generation)
                            coordinator.plan.value?.takeIf { it.desired }?.let { replacement ->
                                restartRecoveryGeneration = replacement.generation
                                restartRecoveryExpiresAtNs = SystemClock.elapsedRealtimeNanos() + RECOVERY_NO_CONSUMER_PERMIT_NS
                            }
                            }
                            else -> retryDelayMs = INITIAL_RETRY_DELAY_MS
                        }
                    }
                    .onFailure { error ->
                        if (PcSyncServiceFaultPolicy.requiresLearnerStop(error.message)) {
                            stopForCredentialRevocation()
                            return@launch
                        } else if (error.message == "pc_delivery_http_404") {
                            stopV2MediaEgress()
                            // A gateway restart loses only its in-memory
                            // supervisor.  Its former runner receives a
                            // parent-loss stop signal and must settle the
                            // currently sealed tail before this Android side
                            // can authorize a replacement.  Restarting in the
                            // same poll created two workers for one RTSP
                            // source.
                            coordinator.report(plan.generation, "RECOVERING", "pc_gateway_restarted_settling_previous_tail")
                            delay(GATEWAY_RESTART_SETTLEMENT_DELAY_MS)
                            val latest = coordinator.plan.value
                            if (latest?.desired == true && latest.generation == plan.generation && latest.sessionId == activeSessionId) {
                                coordinator.restart(plan.generation)
                                coordinator.plan.value?.takeIf { it.desired }?.let { replacement ->
                                    restartRecoveryGeneration = replacement.generation
                                    restartRecoveryExpiresAtNs = SystemClock.elapsedRealtimeNanos() + RECOVERY_NO_CONSUMER_PERMIT_NS
                                }
                            }
                            retryDelayMs = INITIAL_RETRY_DELAY_MS
                        } else {
                            coordinator.report(plan.generation, "RECOVERING", error.message?.take(160) ?: "pc_capture_status_unavailable")
                            runCatching { client.reconnectFromNearbyGateway() }
                            delay(retryDelayMs)
                            retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_DELAY_MS)
                        }
                    }
                delay(CAPTURE_STATUS_INTERVAL_MS)
            }
        }
    }

    private fun stopAuthorizedUserCapture() {
        runCatching { GlobalContext.get().get<RtspTransportFacade>().stopUserCapture() }
            .onFailure { error -> Log.e(TAG, "PC worker failed but active RTSP capture could not be stopped", error) }
    }

    /**
     * A gateway credential rejection is an authorization fence.  It must close
     * transport and durable restart state before any DHCP recovery can run.
     */
    private fun stopForCredentialRevocation() {
        MobileAppServices.pcSyncUserIntentStore(this).recordLearnerStop()
        MobileAppServices.pcCaptureSessionCoordinator(this).requestStop()
        setTransportOutputAllowed(false)
        stopAuthorizedUserCapture()
        stopSelf()
    }

    private fun isTerminal(state: String): Boolean = state in TERMINAL_CAPTURE_STATES || state.startsWith("FAILED")

    override fun onDestroy() {
        stopV2MediaEgress()
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun installV2MediaEgress(
        coordinator: PcCaptureSessionCoordinator,
        session: PcCaptureSession,
    ) {
        val plan = coordinator.plan.value ?: return
        if (!plan.desired || session.state !in setOf("STARTING", "RUNNING")) {
            stopV2MediaEgress()
            setTransportOutputAllowed(false)
            return
        }
        val learnerId = plan.learnerId ?: return setTransportOutputAllowed(false)
        val consentId = plan.captureConsentId ?: return setTransportOutputAllowed(false)
        val consentGeneration = plan.consentGeneration ?: return setTransportOutputAllowed(false)
        val captureEpoch = plan.captureEpoch ?: return setTransportOutputAllowed(false)
        val leaseId = session.mediaRouteLeaseId ?: return setTransportOutputAllowed(false)
        val routeEpoch = session.mediaRouteEpoch ?: return setTransportOutputAllowed(false)
        val sessionId = plan.sessionId ?: return setTransportOutputAllowed(false)
        if (session.captureEpoch != captureEpoch || session.sessionId != sessionId) {
            stopV2MediaEgress()
            setTransportOutputAllowed(false)
            return
        }
        val key = "${plan.generation}:$leaseId:$routeEpoch"
        if (key == v2MediaEgressKey) return
        stopV2MediaEgress()
        val controller = PcV2MediaEgressController(
            MobileAppServices.pcV2MediaSecurityClient(this),
        ) { error ->
            Log.e(TAG, "v2 media egress failed closed: $error")
            stopV2MediaEgress()
            setTransportOutputAllowed(false)
        }
        v2MediaEgress = controller
        v2MediaEgressKey = key
        controller.start(
            V2MediaSecurityBinding(
                learnerId = learnerId,
                captureSessionId = sessionId,
                captureConsentId = consentId,
                consentGeneration = consentGeneration,
                routeLeaseId = leaseId,
                routeEpoch = routeEpoch,
                captureEpoch = captureEpoch,
            ),
        )
        controller.setOutputAllowed(
            plan.captureOutputState in setOf(
                CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS,
                CaptureOutputGateTransition.ALLOWED_SELECTED_APP,
            ),
            leaseDurationMs = if (plan.capturePolicy.mode == PcCaptureMode.SELECTED_APPS) {
                FOREGROUND_OUTPUT_LEASE_MS
            } else {
                null
            },
        )
        runCatching { GlobalContext.get().get<RtspTransportFacade>().setEncodedFrameSink(controller) }
            .onFailure { error ->
                Log.e(TAG, "RTSP encoded sink unavailable", error)
                controller.stop()
                v2MediaEgress = null
                v2MediaEgressKey = null
                setTransportOutputAllowed(false)
            }
    }

    private fun stopV2MediaEgress() {
        v2MediaEgress?.stop()
        v2MediaEgress = null
        v2MediaEgressKey = null
        runCatching { GlobalContext.get().get<RtspTransportFacade>().setEncodedFrameSink(null) }
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
            .setContentText("已配对 PC 的实时学习同步服务正在运行")
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
        private const val ACTION_CAPTURE_STARTED: String = "cn.zhixingzhixue.edge.action.START_PC_CAPTURE"
        private const val ACTION_CAPTURE_STOPPED: String = "cn.zhixingzhixue.edge.action.STOP_PC_CAPTURE"
        private const val EXTRA_RTSP_PORT: String = "rtsp_port"
        private const val EXTRA_RTSP_PATH: String = "rtsp_path"
        private const val EXTRA_CAPTURE_MODE: String = "capture_mode"
        private const val EXTRA_SELECTED_PACKAGES: String = "selected_packages"
        private const val CHANNEL_ID: String = "pc_delivery_sync_v1"
        private const val NOTIFICATION_ID: Int = 12041
        private const val TAG: String = "PcSyncForegroundService"
        private const val NORMAL_SYNC_INTERVAL_MS: Long = 15_000
        private const val CAPTURE_STATUS_INTERVAL_MS: Long = 5_000
        private const val SYNC_FRAME_INTERVAL_MS: Long = 2_000
        private const val SYNC_FRAME_IDLE_RECHECK_MS: Long = 500
        private const val AUDIO_CAPABILITY_REPORT_INTERVAL_MS: Long = 1_000
        private const val FOREGROUND_OBSERVATION_POLL_MS: Long = 100
        private const val FOREGROUND_OUTPUT_LEASE_MS: Long = 350
        private const val USAGE_STATS_LOOKBACK_MS: Long = 2 * 60 * 1000
        // The PC runner polls its owner every 500 ms, then allows its current
        // RTSP fragment to seal before the regular tail settlement path.  This
        // grace is only used after a gateway-session 404, never in the healthy
        // capture path.
        private const val GATEWAY_RESTART_SETTLEMENT_DELAY_MS: Long = 12_000
        private const val MAX_MEDIA_EMIT_AGE_NS: Long = 8_000_000_000L
        private const val RECOVERY_NO_CONSUMER_PERMIT_NS: Long = 60_000_000_000L
        private const val INITIAL_RETRY_DELAY_MS: Long = 3_000
        private const val MAX_RETRY_DELAY_MS: Long = 60_000
        private val TERMINAL_CAPTURE_STATES: Set<String> = setOf("COMPLETED", "STOPPED", "INTERRUPTED")
        private val ACTIVE_RTSP_STATES: Set<RtspTransportStatus> = setOf(RtspTransportStatus.STREAMING, RtspTransportStatus.STREAMING_NO_CONSUMER)

        public fun start(context: Context) {
            MobileAppServices.pcLinkStore(context).read() ?: return
            if (!MobileAppServices.pcSyncUserIntentStore(context).read(hasPairedPc = true).permitsServiceStart(hasPairedPc = true)) return
            ContextCompat.startForegroundService(context, Intent(context, PcSyncForegroundService::class.java))
        }

        public fun stop(context: Context) {
            // Persist before asking Android to deliver the stop command: the
            // process can die between those operations, but its next restore
            // still has to remain stopped.
            MobileAppServices.pcSyncUserIntentStore(context).recordLearnerStop()
            MobileAppServices.pcCaptureSessionCoordinator(context).requestStop()
            ContextCompat.startForegroundService(
                context,
                Intent(context, PcSyncForegroundService::class.java).setAction(ACTION_STOP),
            )
        }

        public fun startCapture(context: Context, rtspPort: Int, rtspPath: String) {
            startCapture(context, rtspPort, rtspPath, PcCaptureModePolicy.fullContinuous())
        }

        public fun startCapture(context: Context, rtspPort: Int, rtspPath: String, capturePolicy: PcCaptureModePolicy) {
            // This action follows a fresh learner MediaProjection start. It is
            // the only automatic-path caller permitted to reopen a stop fence.
            MobileAppServices.pcSyncUserIntentStore(context).recordExplicitStart()
            ContextCompat.startForegroundService(
                context,
                Intent(context, PcSyncForegroundService::class.java)
                    .setAction(ACTION_CAPTURE_STARTED)
                    .putExtra(EXTRA_RTSP_PORT, rtspPort)
                    .putExtra(EXTRA_RTSP_PATH, rtspPath)
                    .putExtra(EXTRA_CAPTURE_MODE, capturePolicy.mode.name)
                    .putStringArrayListExtra(EXTRA_SELECTED_PACKAGES, ArrayList(capturePolicy.selectedPackages.sorted())),
            )
        }

        public fun stopCapture(context: Context) {
            // Persist the capture fence before the asynchronous service handoff
            // so a process restart cannot recreate a PC consumer in between.
            MobileAppServices.pcCaptureSessionCoordinator(context).requestStop()
            ContextCompat.startForegroundService(
                context,
                Intent(context, PcSyncForegroundService::class.java).setAction(ACTION_CAPTURE_STOPPED),
            )
        }
    }
}
