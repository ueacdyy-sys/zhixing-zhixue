package info.dvkr.screenstream

import info.dvkr.screenstream.common.CommonKoinModule
import info.dvkr.screenstream.rtsp.RtspKoinModule
import org.koin.core.module.Module

public class ScreenStreamApp : BaseApp() {

    /** RTSP is the sole mobile-media transport. MJPEG is intentionally not registered. */
    override val streamingModules: Array<Module> = arrayOf(CommonKoinModule, RtspKoinModule)
}
