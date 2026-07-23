"""
Knowledge Graph & Memory Decay Engine for Agentic OS
======================================================
Provides an SQLite-backed property graph memory storing entities, relations,
confidence scores, source lineage, memory decay metrics, and idle memory deduplication.
"""

from __future__ import annotations

import sqlite3
import json
import time
import math
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class KnowledgeGraphMemory:
    """
    SQLite-backed Graph Memory for Agentic OS.
    Stores entities, relations, timestamps, decay scores, and cryptographic lineage.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".agentic_os" / "memory_graph.sqlite"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    properties_json TEXT,
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER DEFAULT 1
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source_conversation_id TEXT,
                    lineage_hash TEXT,
                    created_at REAL,
                    last_accessed REAL,
                    decay_score REAL DEFAULT 1.0,
                    FOREIGN KEY(subject_id) REFERENCES entities(entity_id),
                    FOREIGN KEY(object_id) REFERENCES entities(entity_id)
                )
            """)
            conn.commit()

    def add_entity(self, entity_id: str, entity_type: str = "concept", properties: Optional[Dict[str, Any]] = None) -> str:
        now = time.time()
        props_str = json.dumps(properties or {})
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entities (entity_id, entity_type, properties_json, created_at, last_accessed, access_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(entity_id) DO UPDATE SET
                    properties_json=?,
                    last_accessed=?,
                    access_count=access_count+1
            """, (entity_id, entity_type, props_str, now, now, props_str, now))
            conn.commit()
        return entity_id

    def add_relation(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float = 1.0,
        source_conversation_id: str = "system",
        properties: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.add_entity(subject_id)
        self.add_entity(object_id)
        now = time.time()
        raw_sig = f"{subject_id}:{predicate}:{object_id}:{source_conversation_id}:{now}"
        relation_id = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]
        lineage_hash = hashlib.sha256(f"{relation_id}:{source_conversation_id}".encode("utf-8")).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO relations (relation_id, subject_id, predicate, object_id, confidence, source_conversation_id, lineage_hash, created_at, last_accessed, decay_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0)
            """, (relation_id, subject_id, predicate, object_id, confidence, source_conversation_id, lineage_hash, now, now))
            conn.commit()
        return relation_id

    def query_relations(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        object_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = "SELECT relation_id, subject_id, predicate, object_id, confidence, source_conversation_id, decay_score, created_at FROM relations WHERE 1=1"
        params: List[Any] = []
        if subject_id:
            query += " AND subject_id=?"
            params.append(subject_id)
        if predicate:
            query += " AND predicate=?"
            params.append(predicate)
        if object_id:
            query += " AND object_id=?"
            params.append(object_id)
        query += " ORDER BY (confidence * decay_score) DESC LIMIT ?"
        params.append(limit)

        results = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for row in cursor.execute(query, params).fetchall():
                results.append({
                    "relation_id": row[0],
                    "subject": row[1],
                    "predicate": row[2],
                    "object": row[3],
                    "confidence": row[4],
                    "source": row[5],
                    "decay_score": row[6],
                    "created_at": row[7],
                })
        return results

    def apply_decay(self, half_life_days: float = 30.0):
        """Recalculates decay scores for memories based on age and access recency."""
        now = time.time()
        half_life_seconds = half_life_days * 86400.0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT relation_id, last_accessed, decay_score FROM relations").fetchall()
            for rel_id, last_access, current_decay in rows:
                age = max(0.0, now - last_access)
                new_decay = math.exp(-math.log(2) * (age / half_life_seconds))
                cursor.execute("UPDATE relations SET decay_score=? WHERE relation_id=?", (new_decay, rel_id))
            conn.commit()

    def consolidate_memories(self) -> Dict[str, Any]:
        """Idle memory consolidation: deduplicates redundant relations and applies decay."""
        self.apply_decay()
        merged_count = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM relations WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM relations GROUP BY subject_id, predicate, object_id
                )
            """)
            merged_count = cursor.rowcount
            conn.commit()
        return {"status": "success", "deduplicated_relations": merged_count}
