package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

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
        assertTrue(projection.snapshot.nodes.all { it.reviewStatus == KnowledgeGraphReviewStatus.PENDING_STUDENT })
    }

    @Test
    fun `student can create and link an editable knowledge note without fabricated media evidence`() {
        val now = OffsetDateTime.parse("2026-07-22T15:01:00+08:00")
        val root = KnowledgeGraphNode(
            id = KnowledgeGraphNodeId("topic:algorithm"),
            type = KnowledgeGraphNodeType.INTEREST_TOPIC,
            label = "算法",
            sessionId = MobileSessionId("session-1"),
            evidenceRefs = listOf(LocalEvidenceRef("local://pc/window-1/vlm.json")),
            updatedAt = now,
        )
        val withNote = KnowledgeGraphEditor.createStudentNode(
            existing = KnowledgeGraphSnapshot(nodes = listOf(root), edges = emptyList()),
            draft = StudentKnowledgeNodeDraft(
                id = KnowledgeGraphNodeId("student:binary-search"),
                label = "二分查找",
                sessionId = MobileSessionId("session-1"),
                note = "在有序数组中每次排除一半区间。",
            ),
            now = now,
        )
        val linked = KnowledgeGraphEditor.createStudentEdge(
            existing = withNote,
            draft = StudentKnowledgeEdgeDraft(
                id = KnowledgeGraphEdgeId("student-edge:algorithm-binary-search"),
                from = root.id,
                to = KnowledgeGraphNodeId("student:binary-search"),
                relationship = KnowledgeRelationship.PART_OF,
            ),
            now = now,
        )

        val note = linked.nodes.single { it.id.value == "student:binary-search" }
        assertEquals(KnowledgeGraphNodeOrigin.STUDENT_CREATED, note.origin)
        assertEquals(KnowledgeGraphReviewStatus.CONFIRMED, note.reviewStatus)
        assertTrue(note.evidenceRefs.isEmpty())
        assertEquals(1, linked.edges.size)
    }

    @Test
    fun `deleting a knowledge node removes all attached relationships`() {
        val now = OffsetDateTime.parse("2026-07-22T15:01:00+08:00")
        val first = KnowledgeGraphNode(
            id = KnowledgeGraphNodeId("a"), type = KnowledgeGraphNodeType.SUBJECT_KNOWLEDGE,
            label = "A", sessionId = MobileSessionId("session-1"), evidenceRefs = emptyList(),
            updatedAt = now, origin = KnowledgeGraphNodeOrigin.STUDENT_CREATED,
            reviewStatus = KnowledgeGraphReviewStatus.CONFIRMED,
        )
        val second = first.copy(id = KnowledgeGraphNodeId("b"), label = "B")
        val graph = KnowledgeGraphEditor.createStudentEdge(
            KnowledgeGraphSnapshot(listOf(first, second), emptyList()),
            StudentKnowledgeEdgeDraft(KnowledgeGraphEdgeId("a-b"), first.id, second.id, KnowledgeRelationship.RELATED_TO),
            now,
        )

        val afterDelete = KnowledgeGraphEditor.removeNode(graph, first.id)
        assertEquals(listOf(second), afterDelete.nodes)
        assertTrue(afterDelete.edges.isEmpty())
    }
}
