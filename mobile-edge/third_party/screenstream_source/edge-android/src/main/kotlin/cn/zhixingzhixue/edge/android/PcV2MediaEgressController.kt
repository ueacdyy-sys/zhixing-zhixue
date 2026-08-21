package cn.zhixingzhixue.edge.android

import info.dvkr.screenstream.rtsp.RtspEncodedFrame
import info.dvkr.screenstream.rtsp.RtspEncodedFrameSink
import info.dvkr.screenstream.rtsp.RtspEncodedTrack
import info.dvkr.screenstream.rtsp.RtspEncodedVideoCodec
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicBoolean
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

internal enum class PcV2MediaEgressOfferResult { ACCEPTED, OUTPUT_BLOCKED, OVER_LIMIT, QUEUE_CLOSED }

/** Thread-safe pending-frame queue whose tail can be discarded at a privacy gate boundary. */
internal class PcV2MediaEgressQueue {
    internal val channel: Channel<RtspEncodedFrame> = Channel(Channel.UNLIMITED)
    private val pendingBytes = AtomicLong(0L)
    private val pendingFrames = AtomicInteger(0)
    private val lock = Any()
    private var outputAllowed: Boolean = true

    internal fun offer(frame: RtspEncodedFrame, maxPendingBytes: Long = Long.MAX_VALUE): PcV2MediaEgressOfferResult {
        synchronized(lock) {
            if (!outputAllowed) return PcV2MediaEgressOfferResult.OUTPUT_BLOCKED
            val frameBytes = frame.bytes.size.toLong() + (frame.videoCodecConfigAnnexB?.size ?: 0).toLong()
            val nextBytes = pendingBytes.addAndGet(frameBytes)
            if (nextBytes > maxPendingBytes) {
                pendingBytes.addAndGet(-frameBytes)
                return PcV2MediaEgressOfferResult.OVER_LIMIT
            }
            pendingFrames.incrementAndGet()
            val result = channel.trySend(frame)
            if (result.isFailure) {
                pendingFrames.decrementAndGet()
                pendingBytes.addAndGet(-frameBytes)
                return PcV2MediaEgressOfferResult.QUEUE_CLOSED
            }
            return PcV2MediaEgressOfferResult.ACCEPTED
        }
    }

    internal fun markDequeued(frame: RtspEncodedFrame) {
        pendingFrames.decrementAndGet()
        pendingBytes.addAndGet(-(frame.bytes.size.toLong() + (frame.videoCodecConfigAnnexB?.size ?: 0).toLong()))
    }

    internal fun setOutputAllowed(allowed: Boolean) {
        synchronized(lock) {
            outputAllowed = allowed
            if (!allowed) {
                while (true) {
                    val frame = channel.tryReceive().getOrNull() ?: break
                    markDequeued(frame)
                }
            }
        }
    }

    internal fun pendingCount(): Int = pendingFrames.get()
}

/**
 * The only adapter allowed to turn RTSP codec output into v2 encrypted media.
 * It requires a binding returned by the current PC capture session and has no
 * legacy/plaintext fallback when opening or uploading fails.
 */
public class PcV2MediaEgressController(
    private val mediaClient: PcV2MediaSecurityClient,
    private val onFatal: (String) -> Unit = {},
) : RtspEncodedFrameSink {
    private val scope = CoroutineScope(Dispatchers.IO)
    private var queue: PcV2MediaEgressQueue? = null
    private var worker: Job? = null
    @Volatile private var stopped: Boolean = true
    private val outputAllowed = AtomicBoolean(true)
    private val outputLeaseDeadlineNs = AtomicLong(Long.MAX_VALUE)

    public fun start(binding: V2MediaSecurityBinding) {
        require(binding.captureSessionId.isNotBlank()) { "v2_media_binding_missing" }
        check(worker?.isActive != true) { "v2_media_egress_already_started" }
        // The encoder callback is a real-time producer.  A small bounded
        // channel made transient HTTPS latency fatal after roughly half a
        // second.  Keep the producer non-blocking and absorb normal LAN/TLS
        // jitter in memory; the explicit byte ceiling remains a fail-closed
        // safety boundary for a genuinely dead gateway.
        val pendingQueue = PcV2MediaEgressQueue()
        pendingQueue.setOutputAllowed(outputAllowed.get())
        queue = pendingQueue
        stopped = false
        worker = scope.launch {
            try {
                var session: V2MediaSecuritySession? = null
                for (frame in pendingQueue.channel) {
                    if (!isActive) break
                    pendingQueue.markDequeued(frame)
                    val videoConfig = frame.videoCodecConfigAnnexB
                    require(
                        frame.track != RtspEncodedTrack.VIDEO || frame.videoCodec == RtspEncodedVideoCodec.H264
                    ) { "v2_media_video_codec_unsupported" }
                    require(
                        frame.track != RtspEncodedTrack.VIDEO || !frame.isKeyFrame ||
                            (videoConfig != null && videoConfig.isNotEmpty())
                    ) { "v2_media_h264_keyframe_config_missing" }
                    val durationUs = frame.durationUs ?: continue
                    require(durationUs > 0L) { "v2_media_frame_duration_invalid" }
                    val activeSession = session?.takeIf {
                        it.response.expiresAtMs - System.currentTimeMillis() > REKEY_EARLY_MS
                    } ?: mediaClient.open(binding).also { session = it }
                    session = uploadWithOneSessionRenewal(
                        binding = binding,
                        current = activeSession,
                        ptsStartUs = frame.ptsUs,
                        ptsEndUs = frame.ptsUs + durationUs,
                        encodedBytes = encode(frame),
                    )
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                stopped = true
                onFatal(error.message ?: "v2_media_egress_failed")
            }
        }
    }

    override fun onEncodedFrame(frame: RtspEncodedFrame) {
        if (stopped || !isOutputOpen()) return
        val pendingQueue = queue ?: return
        // RtspEncodedFrame is a callback-owned value.  Copy the byte arrays
        // before retaining them so the encoder may safely reuse its buffers.
        val retained = frame.copy(
            bytes = frame.bytes.copyOf(),
            videoCodecConfigAnnexB = frame.videoCodecConfigAnnexB?.copyOf(),
        )
        when (pendingQueue.offer(retained, MAX_PENDING_BYTES)) {
            PcV2MediaEgressOfferResult.OUTPUT_BLOCKED -> Unit
            PcV2MediaEgressOfferResult.OVER_LIMIT -> {
                stopped = true
                onFatal("v2_media_egress_memory_ceiling")
                worker?.cancel()
            }
            PcV2MediaEgressOfferResult.QUEUE_CLOSED -> {
                if (!stopped) {
                    stopped = true
                    onFatal("v2_media_egress_queue_closed")
                    worker?.cancel()
                }
            }
            PcV2MediaEgressOfferResult.ACCEPTED -> Unit
        }
    }

    /** Fence the producer before dropping unsent frames at a privacy-gate boundary. */
    public fun setOutputAllowed(allowed: Boolean, leaseDurationMs: Long? = null) {
        require(leaseDurationMs == null || leaseDurationMs > 0L) { "v2_media_output_lease_invalid" }
        outputAllowed.set(allowed)
        outputLeaseDeadlineNs.set(
            if (!allowed) 0L
            else leaseDurationMs?.let { System.nanoTime() + it * 1_000_000L } ?: Long.MAX_VALUE,
        )
        queue?.setOutputAllowed(allowed)
    }

    private fun isOutputOpen(): Boolean {
        if (!outputAllowed.get()) return false
        if (System.nanoTime() < outputLeaseDeadlineNs.get()) return true
        setOutputAllowed(false)
        return false
    }

    public fun stop() {
        stopped = true
        queue?.channel?.close()
        queue = null
        worker?.cancel()
        worker = null
    }

    /**
     * A media-security key is intentionally short lived; this rotates it in
     * the same already-authorized capture session.  It never starts or stops
     * MediaProjection and retries only an unequivocally expired/not-found
     * security session.  Other transport/authentication failures remain
     * fail-closed and stop paired-PC egress.
     */
    private suspend fun uploadWithOneSessionRenewal(
        binding: V2MediaSecurityBinding,
        current: V2MediaSecuritySession,
        ptsStartUs: Long,
        ptsEndUs: Long,
        encodedBytes: ByteArray,
    ): V2MediaSecuritySession {
        try {
            mediaClient.upload(current, ptsStartUs, ptsEndUs, encodedBytes)
            return current
        } catch (error: IllegalArgumentException) {
            if (!isExpiredOrMissingSession(error)) throw error
        }
        val renewed = mediaClient.open(binding)
        mediaClient.upload(renewed, ptsStartUs, ptsEndUs, encodedBytes)
        return renewed
    }

    private fun isExpiredOrMissingSession(error: IllegalArgumentException): Boolean =
        error.message == "v2_media_security_session_expired" ||
            error.message == "v2_media_security_http_404"

    private fun encode(frame: RtspEncodedFrame): ByteArray {
        val body = ByteArrayOutputStream(frame.bytes.size + 32)
        DataOutputStream(body).use { output ->
            output.write(MAGIC)
            output.writeByte(if (frame.track == RtspEncodedTrack.VIDEO) 1 else 2)
            output.writeLong(frame.ptsUs)
            output.writeLong(frame.durationUs ?: 0L)
            output.writeBoolean(frame.isKeyFrame)
            val payload = if (frame.track == RtspEncodedTrack.VIDEO && frame.isKeyFrame) {
                frame.videoCodecConfigAnnexB!! + frame.bytes
            } else frame.bytes
            output.writeInt(payload.size)
            output.write(payload)
        }
        return body.toByteArray()
    }

    private companion object {
        private const val MAX_PENDING_BYTES: Long = 128L * 1024L * 1024L
        private const val REKEY_EARLY_MS: Long = 60_000L
        private val MAGIC: ByteArray = "ZHIXING_ENCODED_MEDIA_FRAME.v1\n".toByteArray(Charsets.US_ASCII)
    }
}
