package info.dvkr.screenstream.rtsp

import kotlin.test.Test
import kotlin.test.assertEquals

public class RtspAudioCapabilitySnapshotTest {
    @Test
    public fun `no requested audio is recorded as absent request not silent content`() {
        val snapshot = RtspAudioCapabilitySnapshot.fromRuntime(
            microphoneRequested = false,
            devicePlaybackRequested = false,
            encoderRunning = false,
            captureDisabled = false,
            failureCode = null,
        )

        assertEquals(RtspAudioCaptureMode.NONE, snapshot.captureMode)
        assertEquals(RtspAudioCapabilityStatus.NOT_REQUESTED, snapshot.status)
    }

    @Test
    public fun `requested playback audio stays unverified until a later evidence snapshot proves it`() {
        val snapshot = RtspAudioCapabilitySnapshot.fromRuntime(
            microphoneRequested = false,
            devicePlaybackRequested = true,
            encoderRunning = true,
            captureDisabled = false,
            failureCode = null,
        )

        assertEquals(RtspAudioCaptureMode.PLAYBACK, snapshot.captureMode)
        assertEquals(RtspAudioCapabilityStatus.CAPTURE_ACTIVE_UNVERIFIED, snapshot.status)
    }

    @Test
    public fun `capture failure dominates requested audio and retains a recoverable reason`() {
        val snapshot = RtspAudioCapabilitySnapshot.fromRuntime(
            microphoneRequested = true,
            devicePlaybackRequested = true,
            encoderRunning = false,
            captureDisabled = true,
            failureCode = "AudioRecordDeadObject",
        )

        assertEquals(RtspAudioCaptureMode.MIXED, snapshot.captureMode)
        assertEquals(RtspAudioCapabilityStatus.UNRESOLVED, snapshot.status)
        assertEquals("AudioRecordDeadObject", snapshot.failureCode)
    }
}
