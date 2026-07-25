package cn.zhixingzhixue.edge.android

import cn.zhixingzhixue.learning.application.CandidateNotice
import cn.zhixingzhixue.learning.application.StudentNotificationPort
import cn.zhixingzhixue.learning.domain.CandidateMediaSource
import org.json.JSONObject
import java.time.OffsetDateTime

/** Receives a versioned PC candidate card through the paired LAN outbox. */
public class PcCandidateCardInbox(
    private val cards: AndroidCandidateCardRepository,
    private val notifications: StudentNotificationPort,
) {
    public suspend fun accept(payload: JSONObject): Boolean {
        require(payload.getString("schema_version") == "mobile_result_message.v1") { "mobile_message_schema_unsupported" }
        require(payload.getString("message_type") == "CANDIDATE_CARD") { "mobile_message_type_unsupported" }
        val card = CandidateCardMessageCodec.decode(payload.getJSONObject("candidate_card")) ?: return false
        cards.upsert(card)
        val noticeStillFresh = payload.optString("expires_at")
            .takeIf { it.isNotBlank() }
            ?.let { value -> runCatching { OffsetDateTime.parse(value).isAfter(OffsetDateTime.now()) }.getOrDefault(false) }
            ?: false
        if (
            payload.optBoolean("is_current_visit", false) &&
            noticeStillFresh &&
            card.source == CandidateMediaSource.PHONE_SCREEN &&
            card.isL1Eligible
        ) {
            notifications.show(
                CandidateNotice(
                    notificationId = card.id.value.hashCode(),
                    candidate = card,
                    title = payload.optString("notice_title").takeIf { it.isNotBlank() }?.take(80) ?: "L1 概念小结",
                    message = payload.optString("notice_message").takeIf { it.isNotBlank() }?.take(240) ?: "已为你准备概念小结，点击查看。",
                ),
            )
        }
        return true
    }
}
