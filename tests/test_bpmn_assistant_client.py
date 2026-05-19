"""
Unit tests for bpmn-assistant HTTP client (Phase C1).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.app.bpmn_assistant_client import BpmnAssistantClient, BpmnAssistantError


class TestBpmnAssistantClient(unittest.TestCase):
    """Mocked sidecar client."""

    @patch("backend.app.bpmn_assistant_client.requests.get")
    def test_health_ok(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 200
        client = BpmnAssistantClient(base_url="http://127.0.0.1:8000")
        self.assertTrue(client.health())

    @patch("backend.app.bpmn_assistant_client.requests.post")
    @patch.object(BpmnAssistantClient, "load_api_keys", return_value={"OPENAI_API_KEY": "test"})
    def test_modify_returns_xml(self, _keys: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "bpmn_xml": "<bpmn:definitions/>",
            "bpmn_json": [],
        }
        client = BpmnAssistantClient(base_url="http://127.0.0.1:8000")
        result = client.modify([{"role": "user", "content": "order pizza process"}])
        self.assertIn("bpmn_xml", result)

    @patch.object(BpmnAssistantClient, "load_api_keys", return_value={})
    def test_modify_missing_keys(self, _keys: MagicMock) -> None:
        client = BpmnAssistantClient()
        with self.assertRaises(BpmnAssistantError):
            client.modify([{"role": "user", "content": "test"}])


if __name__ == "__main__":
    unittest.main()
