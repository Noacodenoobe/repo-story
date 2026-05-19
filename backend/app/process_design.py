"""
BPMN process design sessions — Ollama-first, optional sidecar for XML→JSON.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from . import config
from .bpmn_assistant_client import BpmnAssistantClient, BpmnAssistantError
from .bpmn_ollama_generator import generate_bpmn_xml_ollama
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
    engine: str = "ollama"


class ProcessDesignService:
    """Manage design sessions; generate BPMN via local Ollama by default."""

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
        *,
        bpmn_xml: str = "",
    ) -> str:
        """Generate Polish summary via local Bielik (Phase C4)."""
        if not bpmn_json and not bpmn_xml:
            return "Nie udało się wygenerować diagramu BPMN."

        context = json.dumps(bpmn_json, ensure_ascii=False)[:6000] if bpmn_json else bpmn_xml[:4000]
        prompt = (
            f"Opisz po polsku w 4–6 zdaniach ten proces BPMN dla użytkownika nietechnicznego.\n"
            f"Prośba użytkownika: {user_prompt}\n"
            f"Dane procesu:\n{context}\n"
            "Nie wymyślaj kroków spoza danych. Używaj prostego języka."
        )
        if not self.llm.ping() or not self.llm.has_model(config.MODEL_POLISH):
            return "Diagram BPMN został wygenerowany lokalnie (Ollama). Otwórz podgląd po prawej."

        try:
            result = self.llm.generate(
                prompt=prompt,
                model=config.MODEL_POLISH,
                system="Jesteś polskim asystentem procesów biznesowych.",
                temperature=0.2,
            )
            text = (result.response or "").strip()
            return text or "Diagram BPMN został wygenerowany lokalnie (Ollama)."
        except OllamaError as exc:
            logger.warning("Bielik narrative failed: %s", exc)
            return "Diagram BPMN został wygenerowany lokalnie (Ollama)."

    def _generate_via_ollama(
        self,
        message: str,
        existing_xml: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[str, str, List[Dict[str, Any]], str]:
        """Return (xml, model_used, bpmn_json, status)."""
        xml, model_used = generate_bpmn_xml_ollama(
            message,
            existing_xml=existing_xml,
            client=self.llm,
            model=model or config.BPMN_OLLAMA_MODEL,
        )
        bpmn_json = self.bpmn.bpmn_to_json(xml) if self.bpmn.health() else []
        return xml, model_used, bpmn_json, "ollama"

    def _generate_via_sidecar(
        self,
        message_history: List[Dict[str, str]],
        process_payload: Optional[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> tuple[str, str, List[Dict[str, Any]], str]:
        """Cloud sidecar path (only when BPMN_USE_OLLAMA=false)."""
        result = self.bpmn.modify(
            message_history,
            process=process_payload,
            model=model or config.BPMN_ASSISTANT_MODEL,
        )
        bpmn_xml = result.get("bpmn_xml") or ""
        bpmn_json = result.get("bpmn_json") or []
        if isinstance(bpmn_json, dict):
            bpmn_json = [bpmn_json]
        return bpmn_xml, model or config.BPMN_ASSISTANT_MODEL, bpmn_json, "sidecar_cloud"

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

        Default engine: local Ollama (no cloud API keys).
        """
        chat_session = session_id or str(uuid.uuid4())
        status = "ollama"
        engine = "ollama"
        model_used = model or config.BPMN_OLLAMA_MODEL

        existing = self.store.get_process_design_session(design_id) if design_id else None
        history: List[Dict[str, str]] = []
        revision = 1
        title = message[:80]
        existing_xml: Optional[str] = None
        process_payload: Optional[Dict[str, Any]] = None

        if existing:
            history = json.loads(existing.get("history_json") or "[]")
            revision = int(existing.get("revision") or 0) + 1
            title = existing.get("title") or title
            existing_xml = existing.get("bpmn_xml") or None
            if existing_xml:
                process_payload = {
                    "bpmn_xml": existing_xml,
                    "bpmn_json": json.loads(existing.get("bpmn_json") or "[]"),
                }

        message_history = self._build_message_history(history, message)
        bpmn_xml = ""
        bpmn_json: List[Dict[str, Any]] = []

        try:
            if config.BPMN_USE_OLLAMA:
                bpmn_xml, model_used, bpmn_json, engine = self._generate_via_ollama(
                    message,
                    existing_xml=existing_xml,
                    model=model,
                )
                status = "ollama"
            else:
                if not self.bpmn.health():
                    status = "unavailable"
                    raise BpmnAssistantError("Sidecar not running")
                bpmn_xml, model_used, bpmn_json, engine = self._generate_via_sidecar(
                    message_history,
                    process_payload,
                    model=model,
                )
                status = "sidecar_cloud"
        except (OllamaError, BpmnAssistantError) as exc:
            err = str(exc)
            if "missing_api_keys" in err:
                status = "missing_api_keys"
            elif "Ollama" in err or "model" in err.lower():
                status = "ollama_error"
            else:
                status = "error"
            hint = (
                "Sprawdź `ollama serve` i model "
                f"{config.BPMN_OLLAMA_MODEL} (oraz Bielik do opisu)."
                if config.BPMN_USE_OLLAMA
                else "Sidecar wymaga kluczy API w .env — lub ustaw BPMN_USE_OLLAMA=true."
            )
            return ProcessDesignArtifact(
                session_id=chat_session,
                design_id=design_id or str(uuid.uuid4()),
                user_prompt=message,
                narrative_pl=f"Nie udało się wygenerować diagramu BPMN. {hint}\nSzczegóły: {exc}",
                model_used=model_used,
                sidecar_status=status,
                engine=engine,
                revision=revision,
                title=title,
            )

        narrative = self._narrative_from_bpmn_json(
            bpmn_json,
            message,
            bpmn_xml=bpmn_xml,
        )
        new_history = message_history + [{"role": "assistant", "content": narrative}]

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
            sidecar_status=status,
            engine=engine,
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
