"""
Global RAG chat over indexed guides and system profile.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from . import config
from .guide_indexer import GuideIndexer
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient, get_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Jesteś asystentem konfiguracji Linux i narzędzi open source. "
    "Odpowiadasz po polsku, konkretnie, z komendami gdy to potrzebne. "
    "Uwzględniaj profil sprzętu i zainstalowanych narzędzi użytkownika z kontekstu. "
    "Na końcu wymień źródła w formacie [guide:Tytuł / sekcja]."
)


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

    def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run RAG chat: retrieve chunks, generate answer, save history.

        Returns dict with answer, citations, session_id.
        """
        sid = session_id or str(uuid.uuid4())
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
            context_parts.insert(0, f"[Profil systemu]\n{profile['summary_text'][:1500]}")

        context = "\n\n---\n\n".join(context_parts) if context_parts else "(brak kontekstu w bazie)"
        prompt = (
            f"KONTEKST Z BAZY WIEDZY:\n{context}\n\n"
            f"PYTANIE UŻYTKOWNIKA:\n{message}\n\n"
            "Odpowiedz pomocnie po polsku."
        )

        answer = "Nie udało się wygenerować odpowiedzi — sprawdź Ollamę i model Bielik."
        if self.client.ping() and self.client.has_model(config.MODEL_POLISH):
            try:
                result = self.client.generate(
                    prompt=prompt,
                    model=config.MODEL_POLISH,
                    system=_SYSTEM,
                )
                answer = (result.response or "").strip() or answer
            except Exception as exc:  # noqa: BLE001
                logger.error("Chat generation failed: %s", exc)
                answer = f"Błąd generowania: {exc}"

        self.store.add_chat_message(sid, "user", message)
        self.store.add_chat_message(sid, "assistant", answer, citations=citations)

        return {
            "session_id": sid,
            "answer": answer,
            "citations": citations,
        }
