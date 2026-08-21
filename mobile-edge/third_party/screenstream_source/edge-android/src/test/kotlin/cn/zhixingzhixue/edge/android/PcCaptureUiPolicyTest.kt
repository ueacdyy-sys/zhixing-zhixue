package cn.zhixingzhixue.edge.android

import kotlin.test.Test
import kotlin.test.assertEquals

class PcCaptureUiPolicyTest {
    @Test
    fun `reopens selected app policy from durable capture plan`() {
        val plan = PcCapturePlan(
            sessionId = "phone-session",
            rtspPort = 8554,
            rtspPath = "/live",
            deviceId = "android-device",
            spkiSha256 = "spki",
            generation = 4,
            desired = true,
            stopAcknowledged = false,
            pcState = "RUNNING",
            error = null,
            capturePolicy = PcCaptureModePolicy.selectedApps(setOf("tv.danmaku.bili", "com.xingin.xhs")),
        )

        assertEquals(
            CaptureUiSelection(1, setOf("tv.danmaku.bili", "com.xingin.xhs")),
            captureUiSelectionForPlan(plan),
        )
    }

    @Test
    fun `cleared plan returns full continuous default`() {
        assertEquals(CaptureUiSelection(0, emptySet()), captureUiSelectionForPlan(null))
    }
}
