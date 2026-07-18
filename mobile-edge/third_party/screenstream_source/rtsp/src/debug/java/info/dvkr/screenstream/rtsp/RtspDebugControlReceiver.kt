package info.dvkr.screenstream.rtsp

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.elvishew.xlog.XLog
import info.dvkr.screenstream.common.getLog
import info.dvkr.screenstream.common.module.StreamingModuleManager
import info.dvkr.screenstream.rtsp.internal.RtspStreamingService
import info.dvkr.screenstream.rtsp.settings.RtspSettings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import org.koin.core.context.GlobalContext

public class RtspDebugControlReceiver : BroadcastReceiver() {

    public companion object {
        public const val ACTION_ENABLE_AUDIO: String = "info.dvkr.screenstream.dev.DEBUG_ENABLE_RTSP_AUDIO"
        public const val ACTION_STOP_STREAM: String = "info.dvkr.screenstream.dev.DEBUG_STOP_RTSP_STREAM"
        public const val ACTION_START_STREAM: String = "info.dvkr.screenstream.dev.DEBUG_START_RTSP_STREAM"
        public const val ACTION_RESTART_STREAM: String = "info.dvkr.screenstream.dev.DEBUG_RESTART_RTSP_STREAM"

        public const val EXTRA_ENABLE_MIC: String = "enable_mic"
        public const val EXTRA_ENABLE_DEVICE_AUDIO: String = "enable_device_audio"
        public const val EXTRA_RESTART_DELAY_MS: String = "restart_delay_ms"

        private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    }

    override fun onReceive(context: Context, intent: Intent) {
        val pendingResult = goAsync()
        scope.launch {
            try {
                handle(context.applicationContext, intent)
            } catch (cause: Throwable) {
                XLog.e(getLog("RtspDebugControlReceiver", "action=${intent.action}"), cause)
            } finally {
                pendingResult.finish()
            }
        }
    }

    private suspend fun handle(context: Context, intent: Intent) {
        val action = intent.action ?: return
        XLog.i(getLog("RtspDebugControlReceiver", "action=$action"))

        val koin = GlobalContext.get()
        val settings = koin.get<RtspSettings>()
        val module = koin.get<RtspStreamingModule>(qualifier = RtspKoinQualifier)
        val moduleManager = koin.get<StreamingModuleManager>()

        when (action) {
            ACTION_ENABLE_AUDIO -> {
                updateAudioSettings(settings, intent)
            }

            ACTION_STOP_STREAM -> {
                module.stopStream("RtspDebugControlReceiver")
            }

            ACTION_START_STREAM -> {
                ensureRtspModuleRunning(context, moduleManager, module)
                module.sendEvent(
                    RtspStreamingService.InternalEvent.StartStream(
                        permissionEducationShown = false,
                        clearStartupPolicyError = true
                    )
                )
            }

            ACTION_RESTART_STREAM -> {
                updateAudioSettings(settings, intent)
                ensureRtspModuleRunning(context, moduleManager, module)
                module.stopStream("RtspDebugControlReceiver.Restart")
                withTimeoutOrNull(3000) { module.isStreaming.first { isStreaming -> !isStreaming } }
                delay(intent.getLongExtra(EXTRA_RESTART_DELAY_MS, 600L).coerceIn(0L, 5000L))
                module.sendEvent(
                    RtspStreamingService.InternalEvent.StartStream(
                        permissionEducationShown = false,
                        clearStartupPolicyError = true
                    )
                )
            }
        }
    }

    private suspend fun updateAudioSettings(settings: RtspSettings, intent: Intent) {
        val enableMic = intent.getBooleanExtra(EXTRA_ENABLE_MIC, true)
        val enableDeviceAudio = intent.getBooleanExtra(EXTRA_ENABLE_DEVICE_AUDIO, true)
        settings.updateData {
            copy(
                enableMic = enableMic,
                enableDeviceAudio = enableDeviceAudio
            )
        }
        XLog.i(getLog("RtspDebugControlReceiver", "audio enableMic=$enableMic enableDeviceAudio=$enableDeviceAudio"))
    }

    private suspend fun ensureRtspModuleRunning(
        context: Context,
        moduleManager: StreamingModuleManager,
        module: RtspStreamingModule
    ) {
        if (!moduleManager.isActive(RtspStreamingModule.Id)) {
            moduleManager.startModule(RtspStreamingModule.Id, context)
        }
        withTimeoutOrNull(3000) { module.isRunning.first { isRunning -> isRunning } }
    }
}
