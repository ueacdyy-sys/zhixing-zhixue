package cn.zhixingzhixue.edge.android

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdge
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime
import java.util.UUID

/**
 * Durable local outbox for explicit graph changes.  The graph remains usable
 * offline: a local mutation and its pending sync event are committed before a
 * network request is attempted.  This store deliberately contains no media
 * bytes; evidence references stay as the existing local:// identifiers.
 */
public class AndroidKnowledgeGraphEventStore(context: Context) {
    private val database = Database(context.applicationContext)

    @Synchronized
    public fun enqueueNode(operation: String, node: KnowledgeGraphNode): String = enqueue(
        entityKind = "NODE",
        entityId = node.id.value,
        operation = operation,
        payload = JSONObject()
            .put("node_type", node.type.name)
            .put("label", node.label)
            .put("session_id", node.sessionId.value)
            .put("evidence_refs", JSONArray(node.evidenceRefs.map { it.value }))
            .put("origin", node.origin.name)
            .put("review_status", node.reviewStatus.name)
            .put("note", node.note),
    )

    @Synchronized
    public fun enqueueEdge(operation: String, edge: KnowledgeGraphEdge): String = enqueue(
        entityKind = "EDGE",
        entityId = edge.id.value,
        operation = operation,
        payload = JSONObject()
            .put("from", edge.from.value)
            .put("to", edge.to.value)
            .put("relationship", edge.relationship.name)
            .put("evidence_refs", JSONArray(edge.evidenceRefs.map { it.value }))
            .put("confidence", edge.confidence)
            .put("origin", edge.origin.name)
            .put("review_status", edge.reviewStatus.name),
    )

    @Synchronized
    public fun enqueueDelete(entityKind: String, entityId: String): String = enqueue(
        entityKind = entityKind,
        entityId = entityId,
        operation = "DELETE",
        payload = JSONObject().put("deleted", true),
    )

    @Synchronized
    public fun pending(limit: Int = 50): List<JSONObject> = database.readableDatabase.rawQuery(
        "SELECT event_json FROM local_events WHERE state='PENDING' ORDER BY created_at ASC LIMIT ?",
        arrayOf(limit.toString()),
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(JSONObject(cursor.getString(0)))
        }
    }

    /** Local audit material for the graph-management page.  These are real
     * durable outbox entries, not synthesized "history" rows. */
    @Synchronized
    public fun recent(limit: Int = 50): List<KnowledgeGraphEventSummary> = database.readableDatabase.rawQuery(
        "SELECT event_json,state,created_at FROM local_events ORDER BY created_at DESC LIMIT ?",
        arrayOf(limit.toString()),
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) {
                val event = JSONObject(cursor.getString(0))
                add(
                    KnowledgeGraphEventSummary(
                        entityKind = event.getString("entity_kind"),
                        entityId = event.getString("entity_id"),
                        operation = event.getString("operation"),
                        state = cursor.getString(1),
                        occurredAt = event.optString("occurred_at", cursor.getString(2)),
                    ),
                )
            }
        }
    }

    @Synchronized
    public fun markUploadResult(result: JSONObject) {
        val eventId = result.getString("event_id")
        val state = result.getString("state")
        val writable = database.writableDatabase
        when (state) {
            "ACKED", "DUPLICATE" -> writable.execSQL(
                "UPDATE local_events SET state='ACKED' WHERE event_id=?", arrayOf(eventId),
            )
            "CONFLICT" -> writable.execSQL(
                "UPDATE local_events SET state='CONFLICT', conflict_json=? WHERE event_id=?",
                arrayOf(result.toString(), eventId),
            )
            "REJECTED" -> writable.execSQL(
                "UPDATE local_events SET state='REJECTED', conflict_json=? WHERE event_id=?",
                arrayOf(result.toString(), eventId),
            )
        }
        result.optInt("revision", -1).takeIf { it >= 0 }?.let { revision ->
            val event = eventById(eventId) ?: return@let
            writable.execSQL(
                "INSERT OR REPLACE INTO entity_revisions(entity_kind,entity_id,revision) VALUES(?,?,?)",
                arrayOf(event.getString("entity_kind"), event.getString("entity_id"), revision),
            )
        }
    }

    @Synchronized
    public fun isKnown(eventId: String): Boolean = database.readableDatabase.rawQuery(
        "SELECT 1 FROM local_events WHERE event_id=? UNION SELECT 1 FROM applied_remote_events WHERE event_id=? LIMIT 1",
        arrayOf(eventId, eventId),
    ).use { it.moveToFirst() }

    @Synchronized
    public fun markRemoteApplied(event: JSONObject) {
        val sequence = event.getLong("server_sequence")
        val eventId = event.getString("event_id")
        val writable = database.writableDatabase
        writable.beginTransaction()
        try {
            writable.execSQL(
                "INSERT OR IGNORE INTO applied_remote_events(event_id,server_sequence) VALUES(?,?)",
                arrayOf(eventId, sequence),
            )
            writable.execSQL(
                "INSERT OR REPLACE INTO entity_revisions(entity_kind,entity_id,revision) VALUES(?,?,?)",
                arrayOf(event.getString("entity_kind"), event.getString("entity_id"), event.getInt("revision")),
            )
            writable.execSQL("UPDATE sync_state SET cursor=? WHERE singleton=1", arrayOf(sequence))
            writable.setTransactionSuccessful()
        } finally {
            writable.endTransaction()
        }
    }

    @Synchronized
    public fun cursor(): Long = database.readableDatabase.rawQuery(
        "SELECT cursor FROM sync_state WHERE singleton=1", null,
    ).use { cursor -> if (cursor.moveToFirst()) cursor.getLong(0) else 0L }

    private fun enqueue(entityKind: String, entityId: String, operation: String, payload: JSONObject): String {
        val eventId = UUID.randomUUID().toString()
        val revision = revisionFor(entityKind, entityId)
        val event = JSONObject()
            .put("event_id", eventId)
            .put("entity_kind", entityKind)
            .put("entity_id", entityId)
            .put("operation", operation)
            .put("base_revision", revision)
            .put("occurred_at", OffsetDateTime.now().toString())
            .put("payload", payload)
        database.writableDatabase.execSQL(
            "INSERT INTO local_events(event_id,event_json,state,created_at) VALUES(?,?, 'PENDING',?)",
            arrayOf(eventId, event.toString(), OffsetDateTime.now().toString()),
        )
        return eventId
    }

    private fun revisionFor(entityKind: String, entityId: String): Int = database.readableDatabase.rawQuery(
        "SELECT revision FROM entity_revisions WHERE entity_kind=? AND entity_id=?",
        arrayOf(entityKind, entityId),
    ).use { if (it.moveToFirst()) it.getInt(0) else 0 }

    private fun eventById(eventId: String): JSONObject? = database.readableDatabase.rawQuery(
        "SELECT event_json FROM local_events WHERE event_id=?", arrayOf(eventId),
    ).use { if (it.moveToFirst()) JSONObject(it.getString(0)) else null }

    private class Database(context: Context) : SQLiteOpenHelper(context, "zhixing_knowledge_sync.db", null, 1) {
        override fun onCreate(database: SQLiteDatabase) {
            database.execSQL("CREATE TABLE local_events(event_id TEXT PRIMARY KEY,event_json TEXT NOT NULL,state TEXT NOT NULL,conflict_json TEXT,created_at TEXT NOT NULL)")
            database.execSQL("CREATE TABLE entity_revisions(entity_kind TEXT NOT NULL,entity_id TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(entity_kind,entity_id))")
            database.execSQL("CREATE TABLE applied_remote_events(event_id TEXT PRIMARY KEY,server_sequence INTEGER NOT NULL)")
            database.execSQL("CREATE TABLE sync_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),cursor INTEGER NOT NULL)")
            database.execSQL("INSERT INTO sync_state(singleton,cursor) VALUES(1,0)")
        }

        override fun onUpgrade(database: SQLiteDatabase, oldVersion: Int, newVersion: Int): Unit = Unit
    }
}

public data class KnowledgeGraphEventSummary(
    val entityKind: String,
    val entityId: String,
    val operation: String,
    val state: String,
    val occurredAt: String,
)
