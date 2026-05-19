"""
Unit tests for user notes service (Phase A2).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.knowledge_store import KnowledgeStore
from backend.app.user_notes_service import UserNotesService


class TestUserNotesService(unittest.TestCase):
    """UserNotesService with temp SQLite and mocked embeddings."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "test.db"
        self.store = KnowledgeStore(db_path=db_path)
        self.indexer = MagicMock()
        self.indexer._add = MagicMock()
        self.svc = UserNotesService(store=self.store, indexer=self.indexer)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_list_delete(self) -> None:
        note = self.svc.create_note("NoiseTorch", "Ustawienia mikrofonu PipeWire", "audio")
        self.assertIn("id", note)
        items = self.svc.list_notes()
        self.assertEqual(len(items), 1)
        self.indexer._add.assert_called()
        self.assertTrue(self.svc.delete_note(note["id"]))
        self.assertEqual(len(self.svc.list_notes()), 0)

    def test_update_reindexes(self) -> None:
        note = self.svc.create_note("Tytuł", "Treść")
        self.indexer._add.reset_mock()
        updated = self.svc.update_note(note["id"], "Nowy", "Inna treść")
        self.assertEqual(updated["title"], "Nowy")
        self.indexer._add.assert_called()


if __name__ == "__main__":
    unittest.main()
