"""
BPMN process design sessions and sidecar orchestration (Phase C2/C4).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from . import config
from .bpmn_assistant_client import BpmnAssistantClient, BpmnAssistantError
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient, OllamaError, get_client

logger = logging.getLogger(__name__)


class ProcessDesignArtifact(BaseModel):
    """Result of BPMN generation or revision."""

    model_config = ConfigDict(protected_namespaces=())

    session_id: str
    design_id: str
    user_prompt: str
    bpmn_xml: str = ""
    bpmn_json: List[Dict[str, Any]] = Field(default_factory=list)
    narrative_pl: str = ""
    model_used: str = ""
    sidecar_status: str = "ok"
    revision: int = 1
    title: str = ""


class ProcessDesignService:
    """Manage design sessions and call bpmn-assistant sidecar."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        client: Optional[BpmnAssistantClient] = None,
        llm: Optional[OllamaClient] = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.bpmn = client or BpmnAssistantClient()
        self.llm = llm or get_client()

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return all process design sessions."""
        return self.store.list_process_design_sessions()

    def get_session(self, design_id: str) -> Optional[Dict[str, Any]]:
        """Return one session by id."""
        return self.store.get_process_design_session(design_id)

    def _build_message_history(
        self,
        history_json: List[Dict[str, str]],
        message: str,
    ) -> List[Dict[str, str]]:
        items = list(history_json)
        items.append({"role": "user", "content": message})
        return items

    def _narrative_from_bpmn_json(
        self,
        bpmn_json: List[Dict[str, Any]],
        user_prompt: str,
    ) -> str:
        """Generate Polish summary via local Bielik (Phase C4)."""
        if not bpmn_json:
            return "Wygenerowano diagram BPMN — brak szczegółowego opisu elementów."

        compact = json.dumps(bpmn_json, ensure_ascii=False)[:6000]
        prompt = (
            f"Opisz po polsku w 4–6 zdaniach ten proces BPMN dla użytkownika nietechnicznego.\n"
            f"Prośba użytkownika: {user_prompt}\n"
            f"Dane BPMN (JSON): {compact}\n"
            "Nie wymyślaj kroków spoza JSON. Używaj prostego języka."
        )
        if not self.llm.ping() or not self.llm.has_model(config.MODEL_POLISH):
            return "Diagram BPMN został wygenerowany. Otwórz podgląd po prawej stronie."

        try:
            result = self.llm.generate(
                prompt=prompt,
                model=config.MODEL_POLISH,
                system="Jesteś polskim asystentem procesów biznesowych.",
                temperature=0.2,
            )
            text = (result.response or "").strip()
            return text or "Diagram BPMN został wygenerowany."
        except OllamaError as exc:
            logger.warning("Bielik narrative failed: %s", exc)
            return "Diagram BPMN został wygenerowany (opis lokalny niedostępny)."

    def generate(
        self,
        message: str,
        *,
        session_id: Optional[str] = None,
        design_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ProcessDesignArtifact:
        """
        Create or continue a BPMN design session.

        Args:
            message: User process description or revision request.
            session_id: Optional chat session link.
            design_id: Existing design session to revise.
            model: Override sidecar LLM model.

        Returns:
            ProcessDesignArtifact with XML and narrative.
        """
        chat_session = session_id or str(uuid.uuid4())
        sidecar_status = "ok"
        model_used = model or config.BPMN_ASSISTANT_MODEL

        existing = self.store.get_process_design_session(design_id) if design_id else None
        history: List[Dict[str, str]] = []
        revision = 1
        title = message[:80]
        process_payload: Optional[Dict[str, Any]] = None

        if existing:
            history = json.loads(existing.get("history_json") or "[]")
            revision = int(existing.get("revision") or 0) + 1
            title = existing.get("title") or title
            if existing.get("bpmn_xml"):
                process_payload = {
                    "bpmn_xml": existing["bpmn_xml"],
                    "bpmn_json": json.loads(existing.get("bpmn_json") or "[]"),
                }

        message_history = self._build_message_history(history, message)

        try:
            if not self.bpmn.health():
                sidecar_status = "unavailable"
                raise BpmnAssistantError("Sidecar not running")
            result = self.bpmn.modify(
                message_history,
                process=process_payload,
                model=model_used,
            )
        except BpmnAssistantError as exc:
            err = str(exc)
            if "missing_api_keys" in err:
                sidecar_status = "missing_api_keys"
            elif sidecar_status != "unavailable":
                sidecar_status = "error"
            return ProcessDesignArtifact(
                session_id=chat_session,
                design_id=design_id or str(uuid.uuid4()),
                user_prompt=message,
                narrative_pl=(
                    "Nie udało się wygenerować diagramu BPMN. "
                    f"Status sidecar: {sidecar_status}. "
                    "Uruchom docker-compose w /mnt/ollama/projekty/bpmn-assistant "
                    "i uzupełnij klucze API w .env sidecar."
                ),
                model_used=model_used,
                sidecar_status=sidecar_status,
                revision=revision,
                title=title,
            )

        bpmn_xml = result.get("bpmn_xml") or ""
        bpmn_json = result.get("bpmn_json") or []
        if isinstance(bpmn_json, dict):
            bpmn_json = [bpmn_json]

        narrative = self._narrative_from_bpmn_json(bpmn_json, message)
        new_history = message_history + [
            {"role": "assistant", "content": narrative},
        ]

        saved_id = self.store.upsert_process_design_session(
            design_id=design_id,
            chat_session_id=chat_session,
            title=title,
            bpmn_xml=bpmn_xml,
            bpmn_json=bpmn_json,
            history_json=new_history,
            revision=revision,
        )

        return ProcessDesignArtifact(
            session_id=chat_session,
            design_id=saved_id,
            user_prompt=message,
            bpmn_xml=bpmn_xml,
            bpmn_json=bpmn_json,
            narrative_pl=narrative,
            model_used=model_used,
            sidecar_status=sidecar_status,
            revision=revision,
            title=title,
        )

    def revise(
        self,
        design_id: str,
        message: str,
        *,
        model: Optional[str] = None,
    ) -> ProcessDesignArtifact:
        """Edit an existing BPMN session."""
        existing = self.store.get_process_design_session(design_id)
        if not existing:
            raise KeyError(f"Unknown design session: {design_id}")
        return self.generate(
            message,
            session_id=existing.get("session_id"),
            design_id=design_id,
            model=model,
        )
