package cn.zhixingzhixue.learning.domain

import java.time.OffsetDateTime
import kotlin.test.Test
import kotlin.test.assertEquals

public class AgentWorkspaceTest {
    @Test
    public fun `workspace accepts explicit local conversation material without assistant fabrication`() {
        AgentWorkspaceSnapshot(
            messages = listOf(
                AgentConversationMessage(
                    id = "student-1",
                    author = AgentMessageAuthor.STUDENT,
                    body = "请根据这些会话整理复习问题。",
                    createdAt = OffsetDateTime.parse("2026-07-23T10:00:00+08:00"),
                ),
            ),
            contextReferences = emptyList(),
            resources = emptyList(),
        )
    }

    @Test
    public fun `selected attachment remains local queued until a future remote adapter changes it`() {
        val attachment = AgentResourceAttachment(
            id = "resource-1",
            uri = "content://provider/file",
            displayName = "资料.pdf",
            mimeType = "application/pdf",
            addedAt = OffsetDateTime.parse("2026-07-23T10:00:00+08:00"),
        )

        assertEquals(AgentResourceState.LOCAL_QUEUED, attachment.state)
    }
}
