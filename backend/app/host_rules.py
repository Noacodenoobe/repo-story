"""
Index canonical host operating rules into the knowledge base for RAG.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from .guide_indexer import GuideIndexer
from .knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

RULES_SOURCES = [
    Path("/mnt/ollama/system-control/info wazne/regulamin_linux_ai.md"),
    Path("/mnt/ollama/system-control/info wazne/standard_projektu_ai_na_tym_komputerze.md"),
]


def load_rules_text() -> List[Dict[str, str]]:
    """Load rule documents that exist on disk."""
    docs: List[Dict[str, str]] = []
    for path in RULES_SOURCES:
        if path.is_file():
            docs.append({
                "path": str(path),
                "title": path.stem.replace("_", " "),
                "text": path.read_text(encoding="utf-8", errors="replace"),
            })
    return docs


def index_host_rules(store: KnowledgeStore | None = None) -> Dict[str, Any]:
    """Chunk and embed host rules for global RAG (guide_id NULL, source_type rules)."""
    store = store or KnowledgeStore()
    indexer = GuideIndexer(store=store)
    docs = load_rules_text()
    if not docs:
        return {"indexed": 0, "message": "Brak plików zasad na dysku."}

    with store._connect() as conn:
        conn.execute("DELETE FROM chunks WHERE source_type = 'rules'")
        rows = conn.execute(
            "SELECT id FROM chunks WHERE source_type = 'rules'"
        ).fetchall()
        for row in rows:
            conn.execute(
                "DELETE FROM chunk_embeddings WHERE chunk_id = ?", (row["id"],)
            )

    count = 0
    for doc in docs:
        text = doc["text"]
        parts = [text[i : i + 1500] for i in range(0, len(text), 1400)]
        for i, part in enumerate(parts):
            section = f"{doc['title']}:{i + 1}"
            indexer._add(
                None,
                "rules",
                section,
                part,
                {"path": doc["path"], "title": doc["title"]},
            )
            count += 1
    logger.info("Indexed %d host rule chunks", count)
    return {"indexed": count, "files": [d["path"] for d in docs]}
