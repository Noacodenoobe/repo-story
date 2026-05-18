"""
Global RAG chat over indexed guides and system profile.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import config
from .guide_indexer import GuideIndexer
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient, OllamaError, get_client
from .conversation_config import build_system_prompt
from .sse import format_sse_event

logger = logging.getLogger(__name__)

_FALLBACK_ANSWER = (
    "Nie udało się wygenerować odpowiedzi — sprawdź Ollamę i model Bielik."
)


@dataclass
class ChatContext:
    """Prepared RAG context for sync or streaming generation."""

    session_id: str
    message: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    prompt: str = ""
    history_block: str = ""


class RagChatService:
    """Answer user questions using global knowledge base."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        client: Optional[OllamaClient] = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.client = client or get_client()
        self.indexer = GuideIndexer(store=self.store, client=self.client)

    def _resolve_session_id(self, session_id: Optional[str]) -> str:
        return session_id or str(uuid.uuid4())

    def _retrieve(self, message: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Embed query and search knowledge base.

        Returns:
            Tuple of (citations, context_parts for prompt).
        """
        citations: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        try:
            q_emb = self.client.embed(message[:2000])
            hits = self.store.search_chunks(q_emb, top_k=config.TOP_K_RETRIEVAL)
            for score, chunk in hits:
                if score < 0.3:
                    continue
                label = chunk.get("guide_title") or "System"
                section = chunk.get("section") or ""
                citations.append({
                    "guide_id": chunk.get("guide_id"),
                    "guide_title": label,
                    "section": section,
                    "excerpt": chunk["text"][:300],
                    "score": round(score, 3),
                })
                context_parts.append(
                    f"[{label} / {section}]\n{chunk['text'][:800]}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG retrieval failed: %s", exc)

        profile = self.store.get_system_profile()
        if profile and profile.get("summary_text"):
            context_parts.insert(
                0,
                f"[Profil systemu]\n{profile['summary_text'][:1500]}",
            )

        return citations, context_parts

    def _build_history_block(self, session_id: str) -> str:
        """Format recent session messages for multi-turn context."""
        history = self.store.get_chat_history(
            session_id,
            limit=config.CHAT_HISTORY_LIMIT,
        )
        if not history:
            return ""

        lines: List[str] = []
        for msg in history:
            role = msg.get("role", "user")
            if role not in ("user", "assistant"):
                continue
            label = "Użytkownik" if role == "user" else "Asystent"
            content = (msg.get("content") or "").strip()
            if content:
                lines.append(f"{label}: {content[:600]}")

        if not lines:
            return ""
        return "HISTORIA ROZMOWY:\n" + "\n".join(lines) + "\n\n"

    def _build_prompt(
        self,
        message: str,
        context_parts: List[str],
        history_block: str = "",
    ) -> str:
        context = (
            "\n\n---\n\n".join(context_parts)
            if context_parts
            else "(brak kontekstu w bazie)"
        )
        return (
            f"{history_block}"
            f"KONTEKST Z BAZY WIEDZY:\n{context}\n\n"
            f"PYTANIE UŻYTKOWNIKA:\n{message}\n\n"
            "Odpowiedz pomocnie po polsku."
        )

    def prepare_context(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        include_history: bool = True,
    ) -> ChatContext:
        """
        Build retrieval context and prompt without calling the LLM.

        Args:
            message: User question.
            session_id: Optional existing session UUID.
            include_history: Whether to prepend prior turns from SQLite.

        Returns:
            ChatContext ready for generate or stream_generate.
        """
        sid = self._resolve_session_id(session_id)
        citations, context_parts = self._retrieve(message)
        history_block = self._build_history_block(sid) if include_history else ""
        prompt = self._build_prompt(message, context_parts, history_block)
        return ChatContext(
            session_id=sid,
            message=message,
            citations=citations,
            prompt=prompt,
            history_block=history_block,
        )

    def _generate_answer(self, prompt: str, *, voice_mode: bool = False) -> str:
        if not self.client.ping() or not self.client.has_model(config.MODEL_POLISH):
            return _FALLBACK_ANSWER
        try:
            result = self.client.generate(
                prompt=prompt,
                model=config.MODEL_POLISH,
                system=build_system_prompt(voice_mode=voice_mode),
            )
            return (result.response or "").strip() or _FALLBACK_ANSWER
        except (OllamaError, Exception) as exc:  # noqa: BLE001
            logger.error("Chat generation failed: %s", exc)
            return f"Błąd generowania: {exc}"

    def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        voice_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Run RAG chat: retrieve chunks, generate answer, save history.

        Returns:
            Dict with answer, citations, session_id.
        """
        ctx = self.prepare_context(message, session_id)
        answer = self._generate_answer(ctx.prompt, voice_mode=voice_mode)

        self.store.add_chat_message(ctx.session_id, "user", message)
        self.store.add_chat_message(
            ctx.session_id,
            "assistant",
            answer,
            citations=ctx.citations,
        )

        return {
            "session_id": ctx.session_id,
            "answer": answer,
            "citations": ctx.citations,
        }

    def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        voice_mode: bool = False,
    ) -> Iterator[str]:
        """
        Stream RAG chat as SSE-encoded strings.

        Yields:
            SSE blocks: meta (citations), token chunks, done or error.
        """
        ctx = self.prepare_context(message, session_id)
        self.store.add_chat_message(ctx.session_id, "user", message)

        yield format_sse_event(
            "meta",
            {
                "session_id": ctx.session_id,
                "citations": ctx.citations,
            },
        )

        if not self.client.ping():
            yield format_sse_event(
                "error",
                {"detail": "Ollama niedostępna."},
            )
            return

        if not self.client.has_model(config.MODEL_POLISH):
            yield format_sse_event(
                "error",
                {"detail": f"Brak modelu: {config.MODEL_POLISH}"},
            )
            return

        parts: List[str] = []
        try:
            for chunk in self.client.stream_generate(
                prompt=ctx.prompt,
                model=config.MODEL_POLISH,
                system=build_system_prompt(voice_mode=voice_mode),
            ):
                parts.append(chunk)
                yield format_sse_event("token", {"text": chunk})
        except OllamaError as exc:
            logger.error("Chat stream failed: %s", exc)
            yield format_sse_event("error", {"detail": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("Chat stream unexpected error: %s", exc)
            yield format_sse_event("error", {"detail": str(exc)})
            return

        answer = "".join(parts).strip() or _FALLBACK_ANSWER
        self.store.add_chat_message(
            ctx.session_id,
            "assistant",
            answer,
            citations=ctx.citations,
        )

        yield format_sse_event(
            "done",
            {
                "session_id": ctx.session_id,
                "full_answer": answer,
                "citations": ctx.citations,
            },
        )
