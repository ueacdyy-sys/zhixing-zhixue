package info.dvkr.screenstream

import info.dvkr.screenstream.common.CommonKoinModule
import info.dvkr.screenstream.rtsp.RtspKoinModule
import org.koin.core.module.Module

/** 知行智学只装配本地 RTSP 媒体传输，不启用已裁剪的上游功能。 */
public class ScreenStreamApp : BaseApp() {
    override val streamingModules: Array<Module> = arrayOf(CommonKoinModule, RtspKoinModule)
}
