"""
CRUD and RAG indexing for user-authored notes (Phase A2).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from .guide_indexer import GuideIndexer
from .knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class UserNotesService:
    """Manage personal notes stored in SQLite and indexed for RAG."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        indexer: Optional[GuideIndexer] = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.indexer = indexer or GuideIndexer(store=self.store)

    def list_notes(self) -> List[Dict[str, Any]]:
        """Return all user notes sorted by updated_at descending."""
        return self.store.list_user_notes()

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """Return one note or None."""
        return self.store.get_user_note(note_id)

    def create_note(
        self,
        title: str,
        body: str,
        tags: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a note and index it for RAG."""
        note_id = str(uuid.uuid4())
        now = time.time()
        note = {
            "id": note_id,
            "title": title.strip(),
            "body": body.strip(),
            "tags": (tags or "").strip(),
            "created_at": now,
            "updated_at": now,
        }
        self.store.upsert_user_note(note)
        self._index_note(note)
        return note

    def update_note(
        self,
        note_id: str,
        title: str,
        body: str,
        tags: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update note fields and refresh RAG chunks."""
        existing = self.store.get_user_note(note_id)
        if not existing:
            raise KeyError(f"Note not found: {note_id}")
        note = {
            **existing,
            "title": title.strip(),
            "body": body.strip(),
            "tags": (tags or "").strip(),
            "updated_at": time.time(),
        }
        self.store.upsert_user_note(note)
        self.store.delete_chunks_for_user_note(note_id)
        self._index_note(note)
        return note

    def delete_note(self, note_id: str) -> bool:
        """Delete note and its RAG chunks."""
        if not self.store.get_user_note(note_id):
            return False
        self.store.delete_chunks_for_user_note(note_id)
        self.store.delete_user_note(note_id)
        return True

    def reindex_all(self) -> int:
        """Rebuild embeddings for every user note."""
        self.store.delete_all_user_note_chunks()
        count = 0
        for note in self.store.list_user_notes():
            self._index_note(note)
            count += 1
        logger.info("Reindexed %d user notes", count)
        return count

    def _index_note(self, note: Dict[str, Any]) -> None:
        """Chunk and embed a single note."""
        title = note.get("title") or "Notatka"
        body = note.get("body") or ""
        tags = note.get("tags") or ""
        text = f"{title}\n\n{body}"
        if tags:
            text += f"\n\nTagi: {tags}"
        meta = {
            "note_id": note["id"],
            "title": title,
            "tags": tags,
        }
        self.indexer._add(
            guide_id=None,
            source_type="user_note",
            section=title,
            text=text.strip(),
            meta=meta,
        )
