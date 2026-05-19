"""
Unit tests for chat grounding and command sanitization.
"""
from __future__ import annotations

import unittest

from backend.app.chat_grounding import (
    extract_commands_from_context,
    is_meta_system_question,
    sanitize_run_blocks,
)
from backend.app.rag_retrieval import detect_focus_guide


class TestChatGrounding(unittest.TestCase):
    """Grounding helpers."""

    def test_meta_system_question(self) -> None:
        self.assertTrue(
            is_meta_system_question("czy widzisz pliki konfiguracyjne mojego systemu?")
        )

    def test_extract_commands_from_howto(self) -> None:
        ctx = [
            "[Przewodnik: BPMN Asystent / howto]\n"
            "Krok 1: Sklonuj. Komendy: git clone https://github.com/jtlicardo/bpmn-assistant"
        ]
        cmds = extract_commands_from_context(ctx)
        self.assertTrue(any("jtlicardo/bpmn-assistant" in c for c in cmds))

    def test_sanitize_removes_fake_run_blocks(self) -> None:
        ctx = [
            "[howto]\nKomendy: git clone https://github.com/jtlicardo/bpmn-assistant"
        ]
        answer = (
            "OK\n```run\ngit clone https://github.com/fake/repo\n```\n"
            "```run\ngit clone https://github.com/jtlicardo/bpmn-assistant\n```"
        )
        out = sanitize_run_blocks(answer, ctx)
        self.assertNotIn("fake/repo", out)
        self.assertIn("jtlicardo/bpmn-assistant", out)

    def test_focus_bpm_asystent_not_layout(self) -> None:
        guides = [
            {"id": "1", "title": "Przewodnik: BPMN Process Layout Generator", "slug": "bpmn-layout-generators"},
            {"id": "2", "title": "Przewodnik: BPMN Asystent", "slug": "github.com_jtlicardo_bpmn-assistant"},
        ]
        msg = "jak zainstalować tego BPM-asystenta? czy widzisz pliki konfiguracyjne?"
        focus = detect_focus_guide(msg, [], guides)
        self.assertIsNotNone(focus)
        self.assertIn("Asystent", focus["title"])


if __name__ == "__main__":
    unittest.main()
