package cn.zhixingzhixue.edge.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Base64
import androidx.core.app.NotificationCompat
import cn.zhixingzhixue.learning.domain.CandidateCard
import cn.zhixingzhixue.learning.domain.CandidateCardGate
import cn.zhixingzhixue.learning.domain.CandidateCardId
import cn.zhixingzhixue.learning.domain.CandidateEvidenceFact
import cn.zhixingzhixue.learning.domain.CandidateEvidenceLane
import cn.zhixingzhixue.learning.domain.CaptureId
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

/**
 * Privileged diagnostic bridge for a locally authorized edge analyser.
 *
 * The receiver requires android.permission.DUMP, so ordinary third-party apps
 * cannot issue notices.  It accepts only a candidate evidence prompt; neither
 * interest nor learning conclusions cross this boundary.
 */
public class CandidateNoticeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_SHOW_CANDIDATE_NOTICE) return
        val card = candidateCard(
            raw = intent.getStringExtra(EXTRA_CANDIDATE_CARD_JSON),
            encoded = intent.getStringExtra(EXTRA_CANDIDATE_CARD_B64),
        ) ?: return
        runBlocking { AndroidCandidateCardRepository(context.applicationContext).upsert(card) }
        val windowId = intent.getStringExtra(EXTRA_WINDOW_ID)?.takeIf { it.isNotBlank() } ?: return
        val title = intent.getStringExtra(EXTRA_TITLE)?.take(80) ?: "发现一段可回看内容"
        val message = intent.getStringExtra(EXTRA_MESSAGE)?.take(240) ?: "已形成候选证据，可自主查看。"
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "知行智学学习提醒", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "基于当前浏览内容的候选证据提醒"
            }
        )
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val pendingIntent = launch?.let {
            PendingIntent.getActivity(
                context,
                windowId.hashCode(),
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
        manager.notify(windowId.hashCode(), notification)
    }

    private fun candidateCard(raw: String?, encoded: String?): CandidateCard? = runCatching {
        val json = raw ?: encoded?.let { token ->
            String(Base64.decode(token, Base64.URL_SAFE or Base64.NO_WRAP), Charsets.UTF_8)
        }
        if (json.isNullOrBlank() || json.length > MAX_CARD_JSON_CHARS) return null
        val document = JSONObject(json)
        if (
            document.optString("schema_version") != "candidate_card.v1" ||
            document.optString("classification") != "CANDIDATE_ONLY" ||
            document.optString("source_context") != "PHONE_DAILY"
        ) {
            return null
        }
        val range = document.getJSONObject("media_range")
        val facts = document.getJSONArray("facts").let { entries ->
            List(entries.length()) { index ->
                entries.getJSONObject(index).let { fact ->
                    CandidateEvidenceFact(
                        CandidateEvidenceLane.valueOf(fact.getString("lane")),
                        fact.getString("text").take(MAX_FACT_CHARS),
                    )
                }
            }
        }
        val refs = document.getJSONArray("facts").let { entries ->
            List(entries.length()) { index ->
                LocalEvidenceRef(entries.getJSONObject(index).getString("evidence_uri"))
            }
        }
        CandidateCardGate.fromTrimodalEvidence(
            id = CandidateCardId(document.getString("card_id")),
            captureId = CaptureId(document.getString("window_id")),
            visitId = document.getString("visit_id"),
            startPtsNs = range.getLong("start_pts_ns"),
            endPtsNs = range.getLong("end_pts_ns"),
            evidenceRefs = refs,
            facts = facts,
            displayExcerpt = document.getString("display_excerpt").take(MAX_EXCERPT_CHARS),
        )
    }.getOrNull()

    public companion object {
        public const val ACTION_SHOW_CANDIDATE_NOTICE: String = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"
        public const val EXTRA_WINDOW_ID: String = "window_id"
        public const val EXTRA_TITLE: String = "title"
        public const val EXTRA_MESSAGE: String = "message"
        public const val EXTRA_CANDIDATE_CARD_JSON: String = "candidate_card_json"
        public const val EXTRA_CANDIDATE_CARD_B64: String = "candidate_card_b64"
        private const val CHANNEL_ID: String = "student_candidate_notice_v1"
        private const val MAX_CARD_JSON_CHARS: Int = 12_000
        private const val MAX_FACT_CHARS: Int = 240
        private const val MAX_EXCERPT_CHARS: Int = 240
    }
}
