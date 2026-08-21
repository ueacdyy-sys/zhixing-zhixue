package cn.zhixingzhixue.edge.android

import kotlin.test.Test
import kotlin.test.assertFailsWith

public class PcCaptureConsentSnapshotTest {
    @Test
    public fun `device id cannot be used as learner identity`() {
        assertFailsWith<IllegalArgumentException> {
            PcCaptureConsentSnapshot("android-device-1", "consent-1", 1L, 1L)
        }
    }

    @Test
    public fun `consent generation and capture epoch are positive`() {
        assertFailsWith<IllegalArgumentException> {
            PcCaptureConsentSnapshot("learner-1", "consent-1", 0L, 1L)
        }
        assertFailsWith<IllegalArgumentException> {
            PcCaptureConsentSnapshot("learner-1", "consent-1", 1L, 0L)
        }
    }
}
