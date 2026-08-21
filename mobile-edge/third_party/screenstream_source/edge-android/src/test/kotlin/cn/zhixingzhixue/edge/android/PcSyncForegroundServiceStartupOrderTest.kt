package cn.zhixingzhixue.edge.android

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Android starts its foreground-service timeout before [PcSyncForegroundService]
 * receives a command.  The production service may therefore not initialize the
 * PC link, capture coordinator, or user-intent store before it has promoted
 * itself with a visible foreground notification.
 *
 * This source-level guard is intentional: the relevant Android lifecycle call
 * is framework-owned and this module's JVM tests do not run an Android Service.
 */
public class PcSyncForegroundServiceStartupOrderTest {
    @Test
    public fun `foreground promotion precedes all MobileAppServices initialization`() {
        val source = File(
            "src/main/kotlin/cn/zhixingzhixue/edge/android/PcSyncForegroundService.kt",
        ).readText()
        val commandStart = source.indexOf("override fun onStartCommand")
        val commandBody = source.substring(commandStart, source.indexOf("/**", commandStart))

        val promotion = commandBody.indexOf("promoteToForeground()")
        val serviceAccess = commandBody.indexOf("val link = MobileAppServices.pcLinkStore")

        assertTrue(promotion >= 0, "onStartCommand must promote the service")
        assertTrue(serviceAccess >= 0, "test requires a service initialization boundary")
        assertTrue(
            promotion < serviceAccess,
            "foreground promotion must happen before MobileAppServices initialization",
        )
    }
}
