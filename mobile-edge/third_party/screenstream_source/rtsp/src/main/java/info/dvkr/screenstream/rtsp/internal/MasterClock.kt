package info.dvkr.screenstream.rtsp.internal

import android.os.SystemClock

internal data class MasterClockSnapshot(
    val sessionEpochId: Long,
    val anchorElapsedRealtimeNs: Long?,
    val anchorWallClockMs: Long?,
    val latestVideoPtsUs: Long?,
    val latestAudioPtsUs: Long?,
    val lastMediaEmitElapsedRealtimeNs: Long?,
    val lastRequestedKeyFramePtsUs: Long?,
    val lastRequestedKeyFrameEmitElapsedRealtimeNs: Long?
)

internal object MasterClock {
    @Volatile
    private var started = false

    @Volatile
    private var startElapsedRealtimeNs: Long = 0L

    @Volatile
    private var startWallClockMs: Long = 0L

    @Volatile
    private var sessionEpochId: Long = 0L

    @Volatile
    private var latestVideoPtsUs: Long? = null

    @Volatile
    private var latestAudioPtsUs: Long? = null

    @Volatile
    private var lastMediaEmitElapsedRealtimeNs: Long? = null

    @Volatile
    private var syncFrameRequested = false

    @Volatile
    private var lastRequestedKeyFramePtsUs: Long? = null

    @Volatile
    private var lastRequestedKeyFrameEmitElapsedRealtimeNs: Long? = null

    @Synchronized
    fun markSyncFrameRequested() {
        syncFrameRequested = true
    }

    @Synchronized
    fun recordRequestedKeyFrameIfPending(presentationTimeUs: Long) {
        if (!syncFrameRequested) return
        syncFrameRequested = false
        lastRequestedKeyFramePtsUs = presentationTimeUs
        lastRequestedKeyFrameEmitElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
    }

    @Synchronized
    fun ensureStarted() {
        if (!started) {
            startElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
            startWallClockMs = System.currentTimeMillis()
            started = true
        }
    }

    fun relativeTimeUs(): Long {
        ensureStarted()
        return (SystemClock.elapsedRealtimeNanos() - startElapsedRealtimeNs) / 1000L
    }

    fun relativeTimeMs(): Long {
        ensureStarted()
        return (SystemClock.elapsedRealtimeNanos() - startElapsedRealtimeNs) / 1_000_000L
    }

    @Synchronized
    fun recordVideoPtsUs(presentationTimeUs: Long) {
        ensureStarted()
        latestVideoPtsUs = presentationTimeUs
        lastMediaEmitElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
    }

    @Synchronized
    fun recordAudioPtsUs(presentationTimeUs: Long) {
        ensureStarted()
        latestAudioPtsUs = presentationTimeUs
        lastMediaEmitElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
    }

    @Synchronized
    fun snapshot(): MasterClockSnapshot = MasterClockSnapshot(
        sessionEpochId = sessionEpochId,
        anchorElapsedRealtimeNs = startElapsedRealtimeNs.takeIf { started },
        anchorWallClockMs = startWallClockMs.takeIf { started },
        latestVideoPtsUs = latestVideoPtsUs,
        latestAudioPtsUs = latestAudioPtsUs,
        lastMediaEmitElapsedRealtimeNs = lastMediaEmitElapsedRealtimeNs,
        lastRequestedKeyFramePtsUs = lastRequestedKeyFramePtsUs,
        lastRequestedKeyFrameEmitElapsedRealtimeNs = lastRequestedKeyFrameEmitElapsedRealtimeNs
    )

    @Synchronized
    fun reset() {
        started = false
        startElapsedRealtimeNs = 0L
        startWallClockMs = 0L
        latestVideoPtsUs = null
        latestAudioPtsUs = null
        lastMediaEmitElapsedRealtimeNs = null
        syncFrameRequested = false
        lastRequestedKeyFramePtsUs = null
        lastRequestedKeyFrameEmitElapsedRealtimeNs = null
        sessionEpochId += 1L
    }
}
