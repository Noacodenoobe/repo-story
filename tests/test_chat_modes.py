"""
Unit tests for chat response mode routing (Phase C0/C2).
"""
from __future__ import annotations

import unittest

from backend.app.intent_router import detect_response_mode


class TestChatModes(unittest.TestCase):
    """Intent router keyword detection."""

    def test_deployment_install_question(self) -> None:
        msg = "chciałbym zainstalować bpmn-assistenta, jakie foldery?"
        self.assertEqual(detect_response_mode(msg), "deployment")

    def test_process_design_diagram(self) -> None:
        msg = "zaprojektuj diagram BPMN procesu zamówienia pizzy"
        self.assertEqual(detect_response_mode(msg), "process_design")

    def test_default_general(self) -> None:
        msg = "co to jest NoiseTorch?"
        self.assertEqual(detect_response_mode(msg), "default")

    def test_assistent_typo_triggers_deployment(self) -> None:
        msg = "bpmn-assistenta instalacja"
        self.assertEqual(detect_response_mode(msg), "deployment")


if __name__ == "__main__":
    unittest.main()
