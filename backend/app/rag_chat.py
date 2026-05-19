"""
Global RAG chat over indexed guides and system profile.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import config
from .bpmn_assistant_client import BpmnAssistantClient
from .chat_grounding import build_grounding_instructions, sanitize_run_blocks
from .conversation_config import build_system_prompt
from .deployment_plan import (
    DeploymentPlan,
    build_deployment_plan,
    deployment_plan_summary_pl,
)
from .guide_indexer import GuideIndexer
from .intent_router import detect_response_mode
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient, OllamaError, get_client
from .process_design import ProcessDesignService
from .rag_retrieval import detect_focus_guide, retrieve_for_chat
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
    focus_guide_title: Optional[str] = None
    focus_guide_slug: Optional[str] = None
    weak_context: bool = False
    missing_howto: bool = False
    context_parts: List[str] = field(default_factory=list)
    response_mode: str = "default"
    deployment_plan: Optional[DeploymentPlan] = None


class RagChatService:
    """Answer user questions using global knowledge base."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        client: Optional[OllamaClient] = None,
        bpmn_client: Optional[BpmnAssistantClient] = None,
        process_design: Optional[ProcessDesignService] = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.client = client or get_client()
        self.indexer = GuideIndexer(store=self.store, client=self.client)
        self.bpmn_client = bpmn_client or BpmnAssistantClient()
        self.process_design = process_design or ProcessDesignService(
            store=self.store,
            client=self.bpmn_client,
            llm=self.client,
        )

    def _resolve_session_id(self, session_id: Optional[str]) -> str:
        return session_id or str(uuid.uuid4())

    def _has_howto_chunks(self, citations: List[Dict[str, Any]]) -> bool:
        return any(
            (c.get("section") or "").lower().startswith("howto")
            for c in citations
            if c.get("guide_id")
        )

    def _retrieve(
        self,
        message: str,
        session_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str], bool, bool]:
        """
        Embed expanded query and search knowledge base.

        Returns:
            Tuple of (citations, context_parts, focus_title, focus_slug, weak, missing_howto).
        """
        try:
            citations, context_parts, focus_title = retrieve_for_chat(
                self.store,
                self.client,
                message,
                session_id,
            )
            guides = self.store.list_guides()
            history = self.store.get_chat_history(session_id, limit=config.CHAT_HISTORY_LIMIT)
            focus = detect_focus_guide(message, history, guides)
            focus_slug = (focus.get("slug") or "") if focus else None

            guide_chunks = [
                c for c in citations
                if c.get("guide_id") and (c.get("score") or 0) >= config.RAG_MIN_SCORE
            ]
            weak = len(guide_chunks) < 1
            missing_howto = bool(focus_title) and not self._has_howto_chunks(citations)
            return citations, context_parts, focus_title, focus_slug, weak, missing_howto
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG retrieval failed: %s", exc)
            return [], [], None, None, True, False

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
        *,
        focus_guide_title: Optional[str] = None,
        weak_context: bool = False,
        missing_howto: bool = False,
        response_mode: str = "default",
    ) -> str:
        context = (
            "\n\n---\n\n".join(context_parts)
            if context_parts
            else "(brak dopasowanych fragmentów w bazie)"
        )
        focus_line = ""
        if focus_guide_title:
            focus_line = (
                f"TEMAT ROZMOWY (priorytet): przewodnik „{focus_guide_title}”.\n\n"
            )
        weak_line = ""
        if weak_context:
            weak_line = (
                "UWAGA: Brak trafnych fragmentów przewodnika w bazie — "
                "nie zgaduj instalacji; powiedz użytkownikowi, czego brakuje.\n\n"
            )
        if missing_howto:
            weak_line += (
                "UWAGA: Wykryto przewodnik, ale brak sekcji howto w kontekście — "
                "nie podawaj git clone ani pip; wskaż lukę.\n\n"
            )
        grounding = build_grounding_instructions(message, context_parts)
        grounding_block = f"INSTRUKCJE DODATKOWE:\n{grounding}\n\n" if grounding else ""

        deployment_hint = ""
        if response_mode == "deployment":
            deployment_hint = (
                "Tryb wdrożenia: na końcu krótko podsumuj plan instalacji z kontekstu. "
                "Użytkownik zobaczy też strukturalny plan w UI.\n\n"
            )

        return (
            f"{history_block}"
            f"{focus_line}"
            f"{weak_line}"
            f"{deployment_hint}"
            f"{grounding_block}"
            f"KONTEKST Z BAZY WIEDZY (jedyne dozwolone źródło faktów):\n{context}\n\n"
            f"AKTUALNE PYTANIE (odpowiedz wyłącznie na to):\n{message}\n\n"
            "Użyj wyłącznie kontekstu powyżej. Nie powtarzaj poprzedniej odpowiedzi, "
            "jeśli pytanie jest uzupełniające. Nie zostawiaj pustych punktów listy."
        )

    def prepare_context(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        include_history: bool = True,
        response_mode_override: Optional[str] = None,
    ) -> ChatContext:
        """
        Build retrieval context and prompt without calling the LLM.

        Args:
            message: User question.
            session_id: Optional existing session UUID.
            include_history: Whether to prepend prior turns from SQLite.
            response_mode_override: Force a response mode (testing).

        Returns:
            ChatContext ready for generate or stream_generate.
        """
        sid = self._resolve_session_id(session_id)
        history = self.store.get_chat_history(sid, limit=config.CHAT_HISTORY_LIMIT)
        sidecar_ok = self.bpmn_client.health()
        mode = response_mode_override or detect_response_mode(
            message,
            history,
            sidecar_healthy=sidecar_ok,
        )

        citations, context_parts, focus_title, focus_slug, weak, missing_howto = (
            self._retrieve(message, sid)
        )
        history_block = self._build_history_block(sid) if include_history else ""

        plan: Optional[DeploymentPlan] = None
        if mode == "deployment":
            plan = build_deployment_plan(
                message,
                citations,
                context_parts,
                focus_guide_title=focus_title,
                focus_guide_slug=focus_slug,
                confidence=0.85 if focus_title else 0.0,
            )

        prompt = self._build_prompt(
            message,
            context_parts,
            history_block,
            focus_guide_title=focus_title,
            weak_context=weak,
            missing_howto=missing_howto,
            response_mode=mode,
        )
        return ChatContext(
            session_id=sid,
            message=message,
            citations=citations,
            prompt=prompt,
            history_block=history_block,
            focus_guide_title=focus_title,
            focus_guide_slug=focus_slug,
            weak_context=weak,
            missing_howto=missing_howto,
            context_parts=context_parts,
            response_mode=mode,
            deployment_plan=plan,
        )

    def _generate_answer(
        self,
        prompt: str,
        *,
        voice_mode: bool = False,
        response_mode: str = "default",
    ) -> str:
        if not self.client.ping() or not self.client.has_model(config.MODEL_POLISH):
            return _FALLBACK_ANSWER
        try:
            result = self.client.generate(
                prompt=prompt,
                model=config.MODEL_POLISH,
                system=build_system_prompt(
                    voice_mode=voice_mode,
                    response_mode=response_mode,
                ),
                temperature=config.CHAT_TEMPERATURE,
            )
            return (result.response or "").strip() or _FALLBACK_ANSWER
        except (OllamaError, Exception) as exc:  # noqa: BLE001
            logger.error("Chat generation failed: %s", exc)
            return f"Błąd generowania: {exc}"

    def _handle_process_design(
        self,
        ctx: ChatContext,
        *,
        voice_mode: bool = False,
    ) -> Dict[str, Any]:
        artifact = self.process_design.generate(
            ctx.message,
            session_id=ctx.session_id,
        )
        answer = artifact.narrative_pl
        if artifact.sidecar_status != "ok":
            answer = artifact.narrative_pl

        self.store.add_chat_message(ctx.session_id, "user", ctx.message)
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
            "response_mode": "process_design",
            "process_design": artifact.model_dump(),
            "sidecar_ok": self.bpmn_client.health(),
        }

    def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        voice_mode: bool = False,
        response_mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run RAG chat: retrieve chunks, generate answer, save history.

        Returns:
            Dict with answer, citations, session_id, optional deployment_plan or process_design.
        """
        ctx = self.prepare_context(
            message,
            session_id,
            response_mode_override=response_mode_override,
        )

        if ctx.response_mode == "process_design":
            return self._handle_process_design(ctx, voice_mode=voice_mode)

        answer = self._generate_answer(
            ctx.prompt,
            voice_mode=voice_mode,
            response_mode=ctx.response_mode,
        )
        answer = sanitize_run_blocks(answer, ctx.context_parts)

        if ctx.response_mode == "deployment" and ctx.deployment_plan:
            summary = deployment_plan_summary_pl(ctx.deployment_plan)
            if summary and summary not in answer:
                answer = f"{summary}\n\n{answer}".strip()

        self.store.add_chat_message(ctx.session_id, "user", message)
        self.store.add_chat_message(
            ctx.session_id,
            "assistant",
            answer,
            citations=ctx.citations,
        )

        result: Dict[str, Any] = {
            "session_id": ctx.session_id,
            "answer": answer,
            "citations": ctx.citations,
            "response_mode": ctx.response_mode,
            "focus_guide": ctx.focus_guide_title,
            "missing_howto": ctx.missing_howto,
        }
        if ctx.deployment_plan:
            result["deployment_plan"] = ctx.deployment_plan.model_dump()
        return result

    def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        *,
        voice_mode: bool = False,
        response_mode_override: Optional[str] = None,
    ) -> Iterator[str]:
        """
        Stream RAG chat as SSE-encoded strings.

        Yields:
            SSE blocks: meta, deployment, bpmn, token, done or error.
        """
        ctx = self.prepare_context(
            message,
            session_id,
            response_mode_override=response_mode_override,
        )
        self.store.add_chat_message(ctx.session_id, "user", message)

        sidecar_ok = self.bpmn_client.health()
        ollama_ok = self.client.ping()
        yield format_sse_event(
            "meta",
            {
                "session_id": ctx.session_id,
                "citations": ctx.citations,
                "focus_guide": ctx.focus_guide_title,
                "weak_context": ctx.weak_context,
                "missing_howto": ctx.missing_howto,
                "response_mode": ctx.response_mode,
                "sidecar_ok": sidecar_ok,
                "ollama_ok": ollama_ok,
                "bpmn_engine": "ollama" if config.BPMN_USE_OLLAMA else "sidecar_cloud",
            },
        )

        if ctx.response_mode == "deployment" and ctx.deployment_plan:
            yield format_sse_event(
                "deployment",
                {"deployment_plan": ctx.deployment_plan.model_dump()},
            )

        if ctx.response_mode == "process_design":
            artifact = self.process_design.generate(
                ctx.message,
                session_id=ctx.session_id,
            )
            if artifact.bpmn_xml:
                yield format_sse_event(
                    "bpmn",
                    {
                        "bpmn_xml": artifact.bpmn_xml,
                        "design_id": artifact.design_id,
                    },
                )
            answer = artifact.narrative_pl
            self.store.add_chat_message(
                ctx.session_id,
                "assistant",
                answer,
                citations=ctx.citations,
            )
            yield format_sse_event("token", {"text": answer})
            yield format_sse_event(
                "done",
                {
                    "session_id": ctx.session_id,
                    "full_answer": answer,
                    "citations": ctx.citations,
                    "response_mode": "process_design",
                    "process_design": artifact.model_dump(),
                    "sidecar_ok": sidecar_ok,
                },
            )
            return

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
                system=build_system_prompt(
                    voice_mode=voice_mode,
                    response_mode=ctx.response_mode,
                ),
                temperature=config.CHAT_TEMPERATURE,
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
        answer = sanitize_run_blocks(answer, ctx.context_parts)

        if ctx.response_mode == "deployment" and ctx.deployment_plan:
            summary = deployment_plan_summary_pl(ctx.deployment_plan)
            if summary and summary not in answer:
                answer = f"{summary}\n\n{answer}".strip()

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
                "response_mode": ctx.response_mode,
                "deployment_plan": (
                    ctx.deployment_plan.model_dump() if ctx.deployment_plan else None
                ),
            },
        )
