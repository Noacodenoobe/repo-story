"""
Unit tests for local BPMN XML extraction (Phase C5).
"""
from __future__ import annotations

import unittest

from backend.app.bpmn_ollama_generator import _extract_xml


class TestBpmnOllamaGenerator(unittest.TestCase):
    """XML extraction helpers."""

    def test_extract_from_code_fence(self) -> None:
        raw = "```xml\n<?xml version=\"1.0\"?><bpmn2:definitions xmlns:bpmn2=\"http://www.omg.org/spec/BPMN/20100524/MODEL\"></bpmn2:definitions>\n```"
        xml = _extract_xml(raw)
        self.assertIn("definitions", xml)

    def test_extract_bare_xml(self) -> None:
        raw = '<?xml version="1.0"?><bpmn:definitions id="D1"></bpmn:definitions>'
        xml = _extract_xml(raw)
        self.assertTrue(xml.startswith("<?xml"))


if __name__ == "__main__":
    unittest.main()
