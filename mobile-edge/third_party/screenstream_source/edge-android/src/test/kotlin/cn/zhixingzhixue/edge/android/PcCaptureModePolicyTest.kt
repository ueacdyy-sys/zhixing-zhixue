package cn.zhixingzhixue.edge.android

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

public class PcCaptureModePolicyTest {
    @Test
    public fun `a stopped sync intent blocks START_STICKY restoration despite an existing PC link`() {
        val intent = PcSyncUserIntent.disabled()

        assertEquals(false, intent.permitsServiceStart(hasPairedPc = true))
    }

    @Test
    public fun `a legacy paired link remains enabled until the learner explicitly stops sync`() {
        val intent = PcSyncUserIntent.fromStoredValue(storedEnabled = null, hasPairedPc = true)

        assertEquals(true, intent.permitsServiceStart(hasPairedPc = true))
        assertEquals(false, intent.withLearnerStop().permitsServiceStart(hasPairedPc = true))
    }

    @Test
    public fun `an explicit new start reopens a prior stop fence only while paired`() {
        val resumed = PcSyncUserIntent.disabled().withExplicitStart()

        assertEquals(true, resumed.permitsServiceStart(hasPairedPc = true))
        assertEquals(false, resumed.permitsServiceStart(hasPairedPc = false))
    }

    @Test
    public fun `gateway credential revocation is a stop condition rather than a DHCP retry`() {
        assertEquals(true, PcSyncServiceFaultPolicy.requiresLearnerStop("pc_delivery_http_401"))
        assertEquals(true, PcSyncServiceFaultPolicy.requiresLearnerStop("pc_delivery_http_403"))
        assertEquals(false, PcSyncServiceFaultPolicy.requiresLearnerStop("pc_delivery_http_500"))
        assertEquals(false, PcSyncServiceFaultPolicy.requiresLearnerStop(null))
    }

    @Test
    public fun `missing PC capture session is gateway recovery rather than a capture authorization revocation`() {
        assertEquals(true, PcSyncServiceFaultPolicy.requiresGatewayCaptureRecovery("pc_delivery_http_404"))
        assertEquals(false, PcSyncServiceFaultPolicy.requiresGatewayCaptureRecovery("pc_delivery_http_401"))
        assertEquals(false, PcSyncServiceFaultPolicy.requiresGatewayCaptureRecovery(null))
    }

    @Test
    public fun `PC media route binds to consent epoch instead of runner generation`() {
        assertEquals(true, isPcIssuedMediaRouteBound(3L, 3L))
        assertEquals(false, isPcIssuedMediaRouteBound(1L, 3L))
        assertEquals(false, isPcIssuedMediaRouteBound(null, 3L))
    }

    @Test
    public fun `full continuous policy permits every foreground package`() {
        val policy = PcCaptureModePolicy.fullContinuous()

        assertEquals(true, policy.allowsOutputFor("com.android.settings"))
    }

    @Test
    public fun `selected apps policy permits only its configured package`() {
        val policy = PcCaptureModePolicy.selectedApps(setOf("tv.danmaku.bili"))

        assertEquals(true, policy.allowsOutputFor("tv.danmaku.bili"))
        assertEquals(false, policy.allowsOutputFor("com.android.settings"))
    }

    @Test
    public fun `selected apps policy rejects an empty package set`() {
        assertFailsWith<IllegalArgumentException> {
            PcCaptureModePolicy.selectedApps(emptySet())
        }
    }

    @Test
    public fun `selected apps output is closed until a foreground application is observed`() {
        val gate = ForegroundAppOutputGate(PcCaptureModePolicy.selectedApps(setOf("tv.danmaku.bili")))

        assertEquals(false, gate.isOutputAllowed)
        assertEquals(CaptureOutputGateTransition.BLOCKED_UNOBSERVED, gate.current.transition)
    }

    @Test
    public fun `selected apps capture begins with paired PC egress closed`() {
        assertEquals(false, PcCaptureModePolicy.selectedApps(setOf("tv.danmaku.bili")).initialPairedPcOutputAllowed)
        assertEquals(true, PcCaptureModePolicy.fullContinuous().initialPairedPcOutputAllowed)
    }

    @Test
    public fun `leaving selected app blocks media without ending the authorized capture`() {
        val gate = ForegroundAppOutputGate(PcCaptureModePolicy.selectedApps(setOf("tv.danmaku.bili")))

        assertEquals(true, gate.observe("tv.danmaku.bili", ForegroundAppObservationSource.ACCESSIBILITY).isOutputAllowed)
        val blocked = gate.observe("com.android.settings", ForegroundAppObservationSource.USAGE_STATS)

        assertEquals(false, blocked.isOutputAllowed)
        assertEquals(CaptureOutputGateTransition.BLOCKED_UNSELECTED_APP, blocked.transition)
        assertEquals(true, blocked.captureSessionRemainsAuthorized)
    }
}
