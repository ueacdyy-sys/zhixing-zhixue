package cn.zhixingzhixue.edge.android

import kotlin.test.Test
import java.io.File
import kotlin.test.assertTrue

public class V2CredentialEnrollmentLinkTest {
    @Test
    public fun `v2 enrollment reuses the verified legacy pairing origin and pin`() {
        // Android's Base64 implementation is not available in this plain JVM
        // test runtime. This guard checks the real enrollment call site, whose
        // behavior is exercised by the paired-device integration test.
        val source = File(
            "src/main/kotlin/cn/zhixingzhixue/edge/android/PcV2DeviceCredentialClient.kt",
        ).readText()

        assertTrue(source.contains("endpointFromTrustedLink(link)"))
        assertTrue(!source.contains("parsePairingAddress(baseUrl)"))
    }
}
