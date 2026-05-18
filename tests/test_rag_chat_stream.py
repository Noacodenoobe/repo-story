"""
Unit tests for RAG chat streaming (Phase 1).
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.app.rag_chat import RagChatService
from backend.app.sse import format_sse_event


def _parse_sse_blocks(raw: str) -> list[tuple[str, dict]]:
    """Parse concatenated SSE blocks into (event, data) pairs."""
    events = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_line = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_line = line[5:].strip()
        if data_line:
            events.append((event_name, json.loads(data_line)))
    return events


class TestSseFormat(unittest.TestCase):
    """SSE formatter tests."""

    def test_format_sse_event_structure(self) -> None:
        block = format_sse_event("token", {"text": "cześć"})
        self.assertIn("event: token\n", block)
        self.assertIn('"text": "cześć"', block)
        self.assertTrue(block.endswith("\n\n"))


class TestRagChatStream(unittest.TestCase):
    """RagChatService.chat_stream with mocked Ollama."""

    def setUp(self) -> None:
        self.store = MagicMock()
        self.store.get_system_profile.return_value = None
        self.store.search_chunks.return_value = []
        self.store.get_chat_history.return_value = []
        self.client = MagicMock()
        self.client.embed.return_value = [0.1] * 8
        self.client.ping.return_value = True
        self.client.has_model.return_value = True
        self.client.stream_generate.return_value = iter(["Witaj", " ", "świecie"])
        self.service = RagChatService(store=self.store, client=self.client)

    def test_chat_stream_emits_meta_token_done(self) -> None:
        raw = "".join(self.service.chat_stream("Co to NoiseTorch?", session_id="sess-1"))
        events = _parse_sse_blocks(raw)
        names = [e[0] for e in events]
        self.assertEqual(names[0], "meta")
        self.assertIn("token", names)
        self.assertEqual(names[-1], "done")

        meta = events[0][1]
        self.assertEqual(meta["session_id"], "sess-1")
        self.assertIn("citations", meta)

        done = events[-1][1]
        self.assertEqual(done["full_answer"], "Witaj świecie")

        self.store.add_chat_message.assert_any_call("sess-1", "user", "Co to NoiseTorch?")
        self.store.add_chat_message.assert_any_call(
            "sess-1",
            "assistant",
            "Witaj świecie",
            citations=meta["citations"],
        )

    def test_chat_stream_ollama_offline(self) -> None:
        self.client.ping.return_value = False
        raw = "".join(self.service.chat_stream("test"))
        events = _parse_sse_blocks(raw)
        self.assertEqual(events[0][0], "meta")
        self.assertEqual(events[1][0], "error")
        self.client.stream_generate.assert_not_called()

    def test_prepare_context_includes_history(self) -> None:
        self.store.get_chat_history.return_value = [
            {"role": "user", "content": "Pierwsze pytanie"},
            {"role": "assistant", "content": "Pierwsza odpowiedź"},
        ]
        ctx = self.service.prepare_context("Drugie pytanie", "sid", include_history=True)
        self.assertIn("HISTORIA ROZMOWY", ctx.prompt)
        self.assertIn("Pierwsze pytanie", ctx.prompt)


class TestChatStreamIntegration(unittest.TestCase):
    """Endpoint generator wiring (no httpx / TestClient required)."""

    def test_endpoint_generator_yields_sse(self) -> None:
        from backend.app.main import rag_chat

        def fake_stream(message: str, session_id=None):
            yield format_sse_event("meta", {"session_id": "x", "citations": []})
            yield format_sse_event("token", {"text": "Hi"})
            yield format_sse_event("done", {"full_answer": "Hi", "session_id": "x"})

        with patch.object(rag_chat, "chat_stream", side_effect=fake_stream):
            def event_generator():
                yield from rag_chat.chat_stream("hello", session_id=None)

            body = "".join(event_generator())
        events = _parse_sse_blocks(body)
        self.assertEqual([e[0] for e in events], ["meta", "token", "done"])


if __name__ == "__main__":
    unittest.main()
