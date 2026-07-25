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
import cn.zhixingzhixue.learning.domain.KnowledgeGraphNodeOrigin
import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjection
import cn.zhixingzhixue.learning.domain.KnowledgeGraphReviewStatus
import cn.zhixingzhixue.learning.domain.KnowledgeGraphProjector
import cn.zhixingzhixue.learning.domain.KnowledgeGraphSnapshot
import cn.zhixingzhixue.learning.domain.KnowledgeRelationship
import cn.zhixingzhixue.learning.domain.LocalEvidenceRef
import cn.zhixingzhixue.learning.domain.MobileProfileUpdate
import cn.zhixingzhixue.learning.domain.MobileSessionId
import cn.zhixingzhixue.learning.domain.PcKnowledgeAnalysisResult
import cn.zhixingzhixue.learning.domain.ProfileEvidenceStatus
import cn.zhixingzhixue.learning.domain.StudentKnowledgeEdgeDraft
import cn.zhixingzhixue.learning.domain.StudentKnowledgeNodeDraft
import cn.zhixingzhixue.learning.domain.KnowledgeGraphEditor
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
    private val eventStore = AndroidKnowledgeGraphEventStore(context.applicationContext)
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

    override suspend fun createStudentNode(draft: StudentKnowledgeNodeDraft): KnowledgeGraphNode {
        val updated = mutateGraph { snapshot ->
            KnowledgeGraphEditor.createStudentNode(snapshot, draft, java.time.OffsetDateTime.now())
        }
        return updated.nodes.first { it.id == draft.id }.also { eventStore.enqueueNode("CREATE", it) }
    }

    override suspend fun updateStudentNode(
        nodeId: KnowledgeGraphNodeId,
        label: String,
        note: String,
    ): KnowledgeGraphNode? {
        val updated = mutateGraph { snapshot ->
            KnowledgeGraphEditor.updateStudentNode(snapshot, nodeId, label, note, java.time.OffsetDateTime.now())
        }
        return updated.nodes.firstOrNull { it.id == nodeId }?.also { eventStore.enqueueNode("STUDENT_PATCH", it) }
    }

    override suspend fun confirmSuggestion(nodeId: KnowledgeGraphNodeId): KnowledgeGraphNode? {
        val updated = mutateGraph { snapshot ->
            KnowledgeGraphEditor.confirmSuggestion(snapshot, nodeId, java.time.OffsetDateTime.now())
        }
        return updated.nodes.firstOrNull { it.id == nodeId }?.also { eventStore.enqueueNode("REVIEW", it) }
    }

    override suspend fun removeNode(nodeId: KnowledgeGraphNodeId): Boolean {
        val before = graph.value
        if (before.nodes.none { it.id == nodeId }) return false
        mutateGraph { snapshot -> KnowledgeGraphEditor.removeNode(snapshot, nodeId) }
        eventStore.enqueueDelete("NODE", nodeId.value)
        before.edges.filter { it.from == nodeId || it.to == nodeId }.forEach { eventStore.enqueueDelete("EDGE", it.id.value) }
        return true
    }

    override suspend fun createStudentEdge(draft: StudentKnowledgeEdgeDraft): KnowledgeGraphEdge {
        val updated = mutateGraph { snapshot ->
            KnowledgeGraphEditor.createStudentEdge(snapshot, draft, java.time.OffsetDateTime.now())
        }
        return updated.edges.first { it.id == draft.id }.also { eventStore.enqueueEdge("CREATE", it) }
    }

    override suspend fun removeEdge(edgeId: KnowledgeGraphEdgeId): Boolean {
        if (graph.value.edges.none { it.id == edgeId }) return false
        mutateGraph { snapshot -> KnowledgeGraphEditor.removeEdge(snapshot, edgeId) }
        eventStore.enqueueDelete("EDGE", edgeId.value)
        return true
    }

    private suspend fun mutateGraph(transform: (KnowledgeGraphSnapshot) -> KnowledgeGraphSnapshot): KnowledgeGraphSnapshot =
        withContext(Dispatchers.IO) {
            synchronized(this@AndroidKnowledgeGraphRepository) {
                val previous = graph.value
                val updated = transform(previous)
                val database = helper.writableDatabase
                database.beginTransaction()
                try {
                    // Student edits must not transiently erase the complete
                    // vault. Apply a delta so a process interruption cannot
                    // turn one note edit into an all-graph data-loss window.
                    val updatedEdgeIds = updated.edges.mapTo(mutableSetOf()) { it.id }
                    val updatedNodeIds = updated.nodes.mapTo(mutableSetOf()) { it.id }
                    previous.edges.filter { it.id !in updatedEdgeIds }.forEach { edge ->
                        database.delete("graph_edges", "edge_id = ?", arrayOf(edge.id.value))
                    }
                    previous.nodes.filter { it.id !in updatedNodeIds }.forEach { node ->
                        database.delete("graph_nodes", "node_id = ?", arrayOf(node.id.value))
                    }
                    updated.nodes.forEach { node -> upsertNode(database, node) }
                    updated.edges.forEach { edge -> upsertEdge(database, edge) }
                    database.setTransactionSuccessful()
                } finally {
                    database.endTransaction()
                }
                graph.value = updated
                updated
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
                node_id, node_type, label, session_id, evidence_refs, updated_at, origin, review_status, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """.trimIndent(),
            arrayOf<Any>(
                node.id.value,
                node.type.name,
                node.label,
                node.sessionId.value,
                encodeRefs(node.evidenceRefs),
                node.updatedAt.toString(),
                node.origin.name,
                node.reviewStatus.name,
                node.note,
            ),
        )
    }

    private fun upsertEdge(database: SQLiteDatabase, edge: KnowledgeGraphEdge) {
        database.execSQL(
            """
            INSERT OR REPLACE INTO graph_edges(
                edge_id, from_node_id, to_node_id, relationship, evidence_refs, confidence, updated_at, origin, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """.trimIndent(),
            arrayOf<Any>(
                edge.id.value,
                edge.from.value,
                edge.to.value,
                edge.relationship.name,
                encodeRefs(edge.evidenceRefs),
                edge.confidence,
                edge.updatedAt.toString(),
                edge.origin.name,
                edge.reviewStatus.name,
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
            "SELECT node_id, node_type, label, session_id, evidence_refs, updated_at, origin, review_status, note FROM graph_nodes",
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
                            origin = KnowledgeGraphNodeOrigin.valueOf(cursor.getString(6)),
                            reviewStatus = KnowledgeGraphReviewStatus.valueOf(cursor.getString(7)),
                            note = cursor.getString(8),
                        ),
                    )
                }
            }
        }
        val edges = database.rawQuery(
            "SELECT edge_id, from_node_id, to_node_id, relationship, evidence_refs, confidence, updated_at, origin, review_status FROM graph_edges",
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
                            origin = KnowledgeGraphNodeOrigin.valueOf(cursor.getString(7)),
                            reviewStatus = KnowledgeGraphReviewStatus.valueOf(cursor.getString(8)),
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
                    updated_at TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    note TEXT NOT NULL
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
                    updated_at TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    review_status TEXT NOT NULL
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

        override fun onUpgrade(database: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            if (oldVersion < 2) {
                database.execSQL(
                    "ALTER TABLE graph_nodes ADD COLUMN origin TEXT NOT NULL DEFAULT 'PC_ANALYSIS_SUGGESTION'",
                )
                database.execSQL(
                    "ALTER TABLE graph_nodes ADD COLUMN review_status TEXT NOT NULL DEFAULT 'PENDING_STUDENT'",
                )
                database.execSQL("ALTER TABLE graph_nodes ADD COLUMN note TEXT NOT NULL DEFAULT ''")
                database.execSQL(
                    "ALTER TABLE graph_edges ADD COLUMN origin TEXT NOT NULL DEFAULT 'PC_ANALYSIS_SUGGESTION'",
                )
                database.execSQL(
                    "ALTER TABLE graph_edges ADD COLUMN review_status TEXT NOT NULL DEFAULT 'PENDING_STUDENT'",
                )
            }
        }

        private companion object {
            private const val DATABASE_NAME: String = "zhixing_knowledge_vault.db"
            private const val DATABASE_VERSION: Int = 2
        }
    }
}
