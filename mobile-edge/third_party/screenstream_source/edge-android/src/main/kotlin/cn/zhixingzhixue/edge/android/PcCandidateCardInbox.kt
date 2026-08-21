package cn.zhixingzhixue.edge.android

import org.json.JSONObject

/**
 * Rejects legacy candidate cards at runtime.
 *
 * v1 data can only be consumed by an explicit, offline migration reader; it
 * must never enter Discover as new content or create a system notification.
 */
public class PcCandidateCardInbox {
    public suspend fun accept(payload: JSONObject): Boolean {
        require(payload.getString("schema_version") == "mobile_result_message.v1") { "mobile_message_schema_unsupported" }
        require(payload.getString("message_type") == "CANDIDATE_CARD") { "mobile_message_type_unsupported" }
        return false
    }
}
