"""
SQLite store for guides, RAG chunks, chat history, and system profile.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import config

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Persistent knowledge base for guides and RAG."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or config.KNOWLEDGE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS guides (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    slug TEXT,
                    title TEXT,
                    created_at REAL,
                    json_path TEXT
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guide_id TEXT,
                    source_type TEXT,
                    section TEXT,
                    text TEXT NOT NULL,
                    metadata_json TEXT,
                    FOREIGN KEY (guide_id) REFERENCES guides(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id INTEGER PRIMARY KEY,
                    model TEXT,
                    vector_blob BLOB,
                    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    citations_json TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS system_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    collected_at REAL,
                    json_blob TEXT,
                    summary_text TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_guide ON chunks(guide_id);
                CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
            """)

    def upsert_guide(
        self,
        guide_id: str,
        url: str,
        slug: str,
        title: str,
        json_path: str,
        created_at: Optional[float] = None,
    ) -> None:
        """Insert or update guide metadata."""
        ts = created_at or time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO guides (id, url, slug, title, created_at, json_path)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url=excluded.url, slug=excluded.slug, title=excluded.title,
                    json_path=excluded.json_path
                """,
                (guide_id, url, slug, title, ts, json_path),
            )

    def delete_chunks_for_guide(self, guide_id: str) -> None:
        """Remove all chunks and embeddings for a guide."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM chunks WHERE guide_id = ?", (guide_id,)
            ).fetchall()
            for row in rows:
                conn.execute(
                    "DELETE FROM chunk_embeddings WHERE chunk_id = ?",
                    (row["id"],),
                )
            conn.execute("DELETE FROM chunks WHERE guide_id = ?", (guide_id,))

    def add_chunk(
        self,
        guide_id: Optional[str],
        source_type: str,
        section: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[np.ndarray] = None,
        model: str = "",
    ) -> int:
        """Add a text chunk and optional embedding. Returns chunk id."""
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO chunks (guide_id, source_type, section, text, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guide_id, source_type, section, text, meta_json),
            )
            chunk_id = int(cur.lastrowid)
            if embedding is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO chunk_embeddings (chunk_id, model, vector_blob)
                    VALUES (?, ?, ?)
                    """,
                    (chunk_id, model or config.MODEL_EMBED, embedding.astype(np.float32).tobytes()),
                )
            return chunk_id

    def search_chunks(
        self,
        query_embedding: np.ndarray,
        top_k: int = 6,
        guide_id: Optional[str] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Cosine similarity search over stored chunk embeddings."""
        q = np.asarray(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm < 1e-9:
            return []
        q = q / q_norm

        with self._connect() as conn:
            if guide_id:
                sql = """
                    SELECT c.id, c.guide_id, c.source_type, c.section, c.text,
                           c.metadata_json, e.vector_blob, g.title AS guide_title
                    FROM chunks c
                    JOIN chunk_embeddings e ON e.chunk_id = c.id
                    LEFT JOIN guides g ON g.id = c.guide_id
                    WHERE c.guide_id = ? OR c.guide_id IS NULL
                """
                rows = conn.execute(sql, (guide_id,)).fetchall()
            else:
                sql = """
                    SELECT c.id, c.guide_id, c.source_type, c.section, c.text,
                           c.metadata_json, e.vector_blob, g.title AS guide_title
                    FROM chunks c
                    JOIN chunk_embeddings e ON e.chunk_id = c.id
                    LEFT JOIN guides g ON g.id = c.guide_id
                """
                rows = conn.execute(sql).fetchall()

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            vec = np.frombuffer(row["vector_blob"], dtype=np.float32)
            vn = np.linalg.norm(vec)
            if vn < 1e-9:
                continue
            score = float(np.dot(q, vec / vn))
            scored.append((score, {
                "chunk_id": row["id"],
                "guide_id": row["guide_id"],
                "source_type": row["source_type"],
                "section": row["section"],
                "text": row["text"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "guide_title": row["guide_title"] or "Profil systemu",
            }))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]

    def save_system_profile(self, profile: Dict[str, Any], summary: str) -> None:
        """Store latest system profile (single row id=1)."""
        blob = json.dumps(profile, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO system_profile (id, collected_at, json_blob, summary_text)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    collected_at=excluded.collected_at,
                    json_blob=excluded.json_blob,
                    summary_text=excluded.summary_text
                """,
                (time.time(), blob, summary),
            )

    def get_system_profile(self) -> Optional[Dict[str, Any]]:
        """Return latest system profile dict or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT collected_at, json_blob, summary_text FROM system_profile WHERE id = 1"
            ).fetchone()
        if not row:
            return None
        return {
            "collected_at": row["collected_at"],
            "profile": json.loads(row["json_blob"] or "{}"),
            "summary_text": row["summary_text"] or "",
        }

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist chat message."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    json.dumps(citations or [], ensure_ascii=False),
                    time.time(),
                ),
            )

    def get_chat_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent messages for a session."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, citations_json, created_at
                FROM chat_messages WHERE session_id = ?
                ORDER BY created_at ASC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "citations": json.loads(r["citations_json"] or "[]"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def stats(self) -> Dict[str, Any]:
        """Return counts for diagnostics UI."""
        with self._connect() as conn:
            guides = conn.execute("SELECT COUNT(*) AS c FROM guides").fetchone()["c"]
            chunks = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
            embedded = conn.execute("SELECT COUNT(*) AS c FROM chunk_embeddings").fetchone()["c"]
            profile = conn.execute(
                "SELECT collected_at FROM system_profile WHERE id = 1"
            ).fetchone()
        return {
            "guides": guides,
            "chunks": chunks,
            "embedded_chunks": embedded,
            "profile_collected_at": profile["collected_at"] if profile else None,
            "db_path": str(self.db_path),
        }
