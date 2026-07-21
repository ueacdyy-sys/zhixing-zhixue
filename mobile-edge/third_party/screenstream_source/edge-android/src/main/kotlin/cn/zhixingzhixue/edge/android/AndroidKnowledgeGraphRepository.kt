package cn.zhixingzhixue.edge.android

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import cn.zhixingzhixue.learning.application.KnowledgeGraphRepository
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdge
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEdgeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNode
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeId
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeType
import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjection
import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjector
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.MobileProfileUpdate
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
import cn.zhixingzhixue.learning.domain.ProfileEvidenceStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.withContext
import org.json.JSONArray

/**
 * Local phone knowledge vault. SQLite is used instead of SharedPreferences so
 * graph, profile and idempotency updates can commit atomically.
 */
public class AndroidKnowledgeGraphRepository(context: Context) : KnowledgeGraphRepository {
    private val helper = Database(context.applicationContext)
    private val graph = MutableStateFlow(readGraph())
    private val profile = MutableStateFlow(readProfile())

    override fun observeGraph(): Flow<KnowledgeGraphSnapshot> = graph

    override fun observeProfile(): Flow<List<MobileProfileUpdate>> = profile

    override suspend fun apply(result: PcKnowledgeAnalysisResult): KnowledgeGraphProjection = withContext(Dispatchers.IO) {
        synchronized(this@AndroidKnowledgeGraphRepository) {
            val database = helper.writableDatabase
            if (alreadyApplied(database, result.resultId)) {
                return@withContext KnowledgeGraphProjection(graph.value, emptyList())
            }
            val projection = KnowledgeGraphProjector.project(graph.value, result)
            database.beginTransaction()
            try {
                projection.snapshot.nodes.forEach { node -> upsertNode(database, node) }
                projection.snapshot.edges.forEach { edge -> upsertEdge(database, edge) }
                projection.profileUpdates.forEach { update -> upsertProfile(database, update) }
                database.execSQL(
                    "INSERT INTO processed_results(result_id) VALUES (?)",
                    arrayOf(result.resultId),
                )
                database.setTransactionSuccessful()
            } finally {
                database.endTransaction()
            }
            graph.value = projection.snapshot
            profile.value = readProfile()
            projection
        }
    }

    private fun alreadyApplied(database: SQLiteDatabase, resultId: String): Boolean =
        database.rawQuery(
            "SELECT 1 FROM processed_results WHERE result_id = ? LIMIT 1",
            arrayOf(resultId),
        ).use { it.moveToFirst() }

    private fun upsertNode(database: SQLiteDatabase, node: KnowledgeGraphNode) {
        database.execSQL(
            """
            INSERT OR REPLACE INTO graph_nodes(
                node_id, node_type, label, session_id, evidence_refs, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """.trimIndent(),
            arrayOf<Any>(
                node.id.value,
                node.type.name,
                node.label,
                node.sessionId.value,
                encodeRefs(node.evidenceRefs),
                node.updatedAt.toString(),
            ),
        )
    }

    private fun upsertEdge(database: SQLiteDatabase, edge: KnowledgeGraphEdge) {
        database.execSQL(
            """
            INSERT OR REPLACE INTO graph_edges(
                edge_id, from_node_id, to_node_id, relationship, evidence_refs, confidence, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """.trimIndent(),
            arrayOf<Any>(
                edge.id.value,
                edge.from.value,
                edge.to.value,
                edge.relationship.name,
                encodeRefs(edge.evidenceRefs),
                edge.confidence,
                edge.updatedAt.toString(),
            ),
        )
    }

    private fun upsertProfile(database: SQLiteDatabase, update: MobileProfileUpdate) {
        database.execSQL(
            """
            INSERT OR REPLACE INTO profile_entries(
                topic, subject_tag, session_id, evidence_status, evidence_refs, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """.trimIndent(),
            arrayOf(
                update.topic,
                update.subjectTag,
                update.sessionId.value,
                update.status.name,
                encodeRefs(update.evidenceRefs),
                update.updatedAt.toString(),
            ),
        )
    }

    private fun readGraph(): KnowledgeGraphSnapshot {
        val database = helper.readableDatabase
        val nodes = database.rawQuery(
            "SELECT node_id, node_type, label, session_id, evidence_refs, updated_at FROM graph_nodes",
            null,
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        KnowledgeGraphNode(
                            id = KnowledgeGraphNodeId(cursor.getString(0)),
                            type = KnowledgeGraphNodeType.valueOf(cursor.getString(1)),
                            label = cursor.getString(2),
                            sessionId = MobileSessionId(cursor.getString(3)),
                            evidenceRefs = decodeRefs(cursor.getString(4)),
                            updatedAt = java.time.OffsetDateTime.parse(cursor.getString(5)),
                        ),
                    )
                }
            }
        }
        val edges = database.rawQuery(
            "SELECT edge_id, from_node_id, to_node_id, relationship, evidence_refs, confidence, updated_at FROM graph_edges",
            null,
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        KnowledgeGraphEdge(
                            id = KnowledgeGraphEdgeId(cursor.getString(0)),
                            from = KnowledgeGraphNodeId(cursor.getString(1)),
                            to = KnowledgeGraphNodeId(cursor.getString(2)),
                            relationship = KnowledgeRelationship.valueOf(cursor.getString(3)),
                            evidenceRefs = decodeRefs(cursor.getString(4)),
                            confidence = cursor.getDouble(5),
                            updatedAt = java.time.OffsetDateTime.parse(cursor.getString(6)),
                        ),
                    )
                }
            }
        }
        return KnowledgeGraphSnapshot(nodes, edges)
    }

    private fun readProfile(): List<MobileProfileUpdate> = helper.readableDatabase.rawQuery(
        "SELECT topic, subject_tag, session_id, evidence_status, evidence_refs, updated_at FROM profile_entries",
        null,
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) {
                add(
                    MobileProfileUpdate(
                        topic = cursor.getString(0),
                        subjectTag = cursor.getString(1),
                        sessionId = MobileSessionId(cursor.getString(2)),
                        status = ProfileEvidenceStatus.valueOf(cursor.getString(3)),
                        evidenceRefs = decodeRefs(cursor.getString(4)),
                        updatedAt = java.time.OffsetDateTime.parse(cursor.getString(5)),
                    ),
                )
            }
        }
    }

    private fun encodeRefs(refs: List<LocalEvidenceRef>): String = JSONArray(refs.map { it.value }).toString()

    private fun decodeRefs(encoded: String): List<LocalEvidenceRef> {
        val array = JSONArray(encoded)
        return List(array.length()) { index -> LocalEvidenceRef(array.getString(index)) }
    }

    private class Database(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {
        override fun onCreate(database: SQLiteDatabase) {
            database.execSQL(
                """
                CREATE TABLE graph_nodes(
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """.trimIndent(),
            )
            database.execSQL(
                """
                CREATE TABLE graph_edges(
                    edge_id TEXT PRIMARY KEY,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """.trimIndent(),
            )
            database.execSQL(
                """
                CREATE TABLE profile_entries(
                    topic TEXT NOT NULL,
                    subject_tag TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    evidence_status TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(topic, session_id)
                )
                """.trimIndent(),
            )
            database.execSQL("CREATE TABLE processed_results(result_id TEXT PRIMARY KEY)")
        }

        override fun onUpgrade(database: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

        private companion object {
            private const val DATABASE_NAME: String = "zhixing_knowledge_vault.db"
            private const val DATABASE_VERSION: Int = 1
        }
    }
}
