"""
Unit tests for process design service (Phase C2).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.knowledge_store import KnowledgeStore
from backend.app.process_design import ProcessDesignService


class TestProcessDesign(unittest.TestCase):
    """Sessions and mocked sidecar."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "test.db"
        self.store = KnowledgeStore(db_path=db)
        self.bpmn = MagicMock()
        self.llm = MagicMock()
        self.svc = ProcessDesignService(store=self.store, client=self.bpmn, llm=self.llm)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch.object(ProcessDesignService, "_generate_via_ollama")
    def test_generate_saves_session(self, mock_ollama: MagicMock) -> None:
        mock_ollama.return_value = (
            '<bpmn2:definitions xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL">'
            '<bpmn2:process id="P1"/></bpmn2:definitions>',
            "qwen3-coder:latest",
            [{"id": "P1"}],
            "ollama",
        )
        self.llm.ping.return_value = True
        self.llm.has_model.return_value = True
        self.llm.generate.return_value = MagicMock(response="Opis procesu po polsku.")
        artifact = self.svc.generate("proces zamówienia pizzy")
        self.assertTrue(artifact.bpmn_xml)
        self.assertEqual(artifact.engine, "ollama")
        self.assertEqual(artifact.sidecar_status, "ollama")
        saved = self.store.get_process_design_session(artifact.design_id)
        self.assertIsNotNone(saved)
        self.assertIn("bpmn_xml", saved)

    def test_revise_unknown_session(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.revise("missing-id", "popraw krok")


if __name__ == "__main__":
    unittest.main()
