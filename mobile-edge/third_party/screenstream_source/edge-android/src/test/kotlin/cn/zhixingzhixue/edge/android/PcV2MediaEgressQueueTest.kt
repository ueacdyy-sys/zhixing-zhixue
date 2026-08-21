package cn.zhixingzhixue.edge.android

import info.dvkr.screenstream.rtsp.RtspEncodedFrame
import info.dvkr.screenstream.rtsp.RtspEncodedTrack
import kotlin.test.Test
import kotlin.test.assertEquals

class PcV2MediaEgressQueueTest {
    @Test
    fun `discard removes frames already queued when output gate closes`() {
        val queue = PcV2MediaEgressQueue()
        queue.offer(
            RtspEncodedFrame(
                track = RtspEncodedTrack.VIDEO,
                ptsUs = 1,
                durationUs = 33_000,
                isKeyFrame = false,
                bytes = ByteArray(128),
            ),
        )

        assertEquals(1, queue.pendingCount())
        queue.setOutputAllowed(false)
        assertEquals(0, queue.pendingCount())
        assertEquals(
            PcV2MediaEgressOfferResult.OUTPUT_BLOCKED,
            queue.offer(
                RtspEncodedFrame(
                    track = RtspEncodedTrack.VIDEO,
                    ptsUs = 2,
                    durationUs = 33_000,
                    isKeyFrame = false,
                    bytes = ByteArray(128),
                ),
            ),
        )
    }
}
