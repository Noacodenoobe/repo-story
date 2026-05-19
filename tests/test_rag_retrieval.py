"""
Unit tests for RAG retrieval query expansion and guide focus.
"""
from __future__ import annotations

import unittest

from backend.app.rag_retrieval import (
    build_retrieval_query,
    detect_focus_guide,
    rank_and_filter_hits,
)


class TestRagRetrieval(unittest.TestCase):
    """Retrieval helpers without live Ollama."""

    def test_detect_bpm_assistant_focus(self) -> None:
        guides = [
            {"id": "1", "title": "Przewodnik: BPMN Asystent", "slug": "github.com_jtlicardo_bpmn-assistant"},
            {"id": "2", "title": "Przewodnik: NoiseTorch", "slug": "noisetorch"},
        ]
        msg = "Czy mogę wykorzystać BPM Assistanta na moim systemie, jakbym musiał go zainstalować?"
        focus = detect_focus_guide(msg, [], guides)
        self.assertIsNotNone(focus)
        self.assertIn("BPMN", focus["title"])

    def test_build_query_includes_history(self) -> None:
        guides = [{"id": "1", "title": "Przewodnik: BPMN Asystent", "slug": "bpmn-assistant"}]
        history = [
            {"role": "user", "content": "Chodzi o BPM Assistanta z GitHub"},
            {"role": "assistant", "content": "Tak, możesz..."},
        ]
        q = build_retrieval_query("A ścieżki na moim dysku?", history, guides)
        self.assertTrue("bpmn" in q.lower() or "bpm" in q.lower())

    def test_rank_prefers_focus_guide(self) -> None:
        hits = [
            (0.8, {"guide_id": "noise", "guide_title": "NoiseTorch", "section": "story", "text": "x", "source_type": "guide"}),
            (0.75, {"guide_id": "bpmn", "guide_title": "BPMN Asystent", "section": "howto", "text": "git clone", "source_type": "guide"}),
            (0.7, {"guide_id": "bpmn", "guide_title": "BPMN Asystent", "section": "howto", "text": "cd bpmn", "source_type": "guide"}),
        ]
        ranked = rank_and_filter_hits(hits, focus_guide_id="bpmn", min_score=0.3, top_k=6)
        self.assertEqual(ranked[0][1]["guide_id"], "bpmn")


if __name__ == "__main__":
    unittest.main()
