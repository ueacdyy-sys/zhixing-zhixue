package cn.zhixingzhixue.learning.application

import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import cn.zhixingzhixue.learning.domain.LearningStage
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.StudentLearningResponse
import java.time.OffsetDateTime
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

public class RecordStudentLearningResponseTest {
    @Test
    public fun `recording is rejected when the currently voluntary learning stage is not eligible`() = runBlocking {
        val journal = RecordingJournal()
        val recorder = RecordStudentLearningResponse(RejectingEligibility(), journal)

        var rejected: Boolean = false
        try {
            recorder.record(response())
        } catch (_: IllegalArgumentException) {
            rejected = true
        }

        assertTrue(rejected)
        assertEquals(0, journal.records.size)
    }

    @Test
    public fun `recording persists only after the eligibility boundary accepts the exact response`() = runBlocking {
        val journal = RecordingJournal()
        val recorder = RecordStudentLearningResponse(AcceptingEligibility(), journal)

        recorder.record(response())

        assertEquals(listOf(response()), journal.records)
    }

    private fun response(): StudentLearningResponse = StudentLearningResponse(
        resultId = "result-1",
        contentId = "content-1",
        visitId = "visit-1",
        source = CandidateMediaSource.PHONE_SCREEN,
        evidenceRefs = listOf(LocalEvidenceRef("local://evidence-1")),
        stage = LearningStage.L3_GUIDED_PRACTICE,
        body = "我保留这一层的练习记录。",
        recordedAt = OffsetDateTime.parse("2026-07-23T11:00:00+08:00"),
    )

    private class RecordingJournal : LearningResponsePort {
        val records: MutableList<StudentLearningResponse> = mutableListOf()

        override fun observe(resultId: String, contentId: String): Flow<List<StudentLearningResponse>> = flowOf(records)

        override suspend fun record(response: StudentLearningResponse) {
            records += response
        }
    }

    private class AcceptingEligibility : LearningResponseEligibilityPort {
        override suspend fun canRecord(response: StudentLearningResponse): Boolean = true
    }

    private class RejectingEligibility : LearningResponseEligibilityPort {
        override suspend fun canRecord(response: StudentLearningResponse): Boolean = false
    }
}
