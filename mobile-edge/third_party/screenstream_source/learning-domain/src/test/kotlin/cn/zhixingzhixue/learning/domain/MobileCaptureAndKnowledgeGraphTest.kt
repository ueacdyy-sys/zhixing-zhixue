package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class MobileCaptureAndKnowledgeGraphTest {
    @Test
    fun `display capture is the required base and platform connector is an additive second layer`() {
        val session = DualLayerCaptureSession(
            sessionId = MobileSessionId("session-1"),
            displayCapture = DisplayLevelCapture(
                captureId = CaptureId("capture-screen-1"),
                consentedAt = OffsetDateTime.parse("2026-07-21T15:00:00+08:00"),
                status = DisplayCaptureStatus.STREAMING,
            ),
            directConnectors = listOf(
                PlatformDirectConnector(
                    connectorId = "public-media-adapter-1",
                    sourceCategory = PublicContentSourceCategory.STREAMING_OR_GRAPHIC,
                    status = DirectConnectorStatus.ACTIVE,
                )
            ),
        )

        assertEquals(DisplayCaptureStatus.STREAMING, session.displayCapture.status)
        assertEquals(1, session.directConnectors.size)
    }

    @Test
    fun `a direct platform connector cannot replace explicit display level consent`() {
        assertFailsWith<IllegalArgumentException> {
            DualLayerCaptureSession(
                sessionId = MobileSessionId("session-1"),
                displayCapture = DisplayLevelCapture(
                    captureId = CaptureId("capture-screen-1"),
                    consentedAt = OffsetDateTime.parse("2026-07-21T15:00:00+08:00"),
                    status = DisplayCaptureStatus.NOT_STARTED,
                ),
                directConnectors = listOf(
                    PlatformDirectConnector(
                        connectorId = "public-media-adapter-1",
                        sourceCategory = PublicContentSourceCategory.STREAMING_OR_GRAPHIC,
                        status = DirectConnectorStatus.ACTIVE,
                    )
                ),
            )
        }
    }

    @Test
    fun `pc result creates evidence linked graph and profile records without ability claims`() {
        val result = PcKnowledgeAnalysisResult(
            resultId = "analysis-1",
            sessionId = MobileSessionId("session-1"),
            visitId = "visit-1",
            createdAt = OffsetDateTime.parse("2026-07-21T15:01:00+08:00"),
            evidenceRefs = listOf(
                LocalEvidenceRef("local://pc/window-1/asr.json"),
                LocalEvidenceRef("local://pc/window-1/ocr.json"),
                LocalEvidenceRef("local://pc/window-1/vlm.json"),
            ),
            associations = listOf(
                KnowledgeAssociation(
                    topic = "二分查找",
                    subjectTag = "算法",
                    relationship = KnowledgeRelationship.MENTIONS_CONCEPT,
                    confidence = 0.78,
                    evidenceRefs = listOf(LocalEvidenceRef("local://pc/window-1/vlm.json")),
                )
            ),
        )

        val projection = KnowledgeGraphProjector.project(KnowledgeGraphSnapshot.empty(), result)

        assertEquals(2, projection.snapshot.nodes.size)
        assertEquals(1, projection.snapshot.edges.size)
        assertEquals("二分查找", projection.profileUpdates.single().topic)
        assertEquals(ProfileEvidenceStatus.CANDIDATE_ONLY, projection.profileUpdates.single().status)
    }
}
