"""
HTTP client for bpmn-assistant sidecar (Phase C1).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from . import config

logger = logging.getLogger(__name__)

_ENV_KEY_RE = re.compile(
    r"^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|FIREWORKS_API_KEY)\s*=\s*(.+)$",
    re.MULTILINE,
)


class BpmnAssistantError(Exception):
    """Sidecar request failed."""


class BpmnAssistantClient:
    """Thin wrapper around bpmn-assistant FastAPI (host port 9748 by default)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or config.BPMN_ASSISTANT_URL).rstrip("/")
        self.timeout_s = timeout_s or config.BPMN_ASSISTANT_TIMEOUT_S

    def health(self) -> bool:
        """Return True when sidecar responds on GET /."""
        if not config.BPMN_ASSISTANT_ENABLED:
            return False
        try:
            resp = requests.get(self.base_url + "/", timeout=min(self.timeout_s, 5))
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def health_detail(self) -> Dict[str, Any]:
        """Extended health: Ollama-first engine status."""
        from .llm_client import get_client

        ollama_ok = get_client().ping()
        sidecar_ok = self.health()
        keys = self.load_api_keys()
        engine = "ollama" if config.BPMN_USE_OLLAMA else "sidecar_cloud"
        return {
            "ok": ollama_ok if config.BPMN_USE_OLLAMA else sidecar_ok,
            "engine": engine,
            "url": self.base_url,
            "enabled": config.BPMN_ASSISTANT_ENABLED,
            "ollama_ok": ollama_ok,
            "ollama_model": config.BPMN_OLLAMA_MODEL,
            "sidecar_ok": sidecar_ok,
            "api_keys_configured": bool(keys),
            "missing_api_keys": not bool(keys) and not config.BPMN_USE_OLLAMA,
            "note": (
                "Diagramy BPMN: lokalny model Ollama (bez kluczy chmurowych)."
                if config.BPMN_USE_OLLAMA
                else "Diagramy BPMN: sidecar wymaga kluczy API w .env."
            ),
        }

    def bpmn_to_json(self, bpmn_xml: str) -> List[Dict[str, Any]]:
        """
        Convert BPMN XML to JSON via sidecar (no LLM keys required).

        Returns:
            Parsed BPMN JSON list or empty list on failure.
        """
        if not bpmn_xml or not self.health():
            return []
        try:
            resp = requests.post(
                f"{self.base_url}/bpmn_to_json",
                json={"bpmn_xml": bpmn_xml},
                timeout=min(self.timeout_s, 60),
            )
            if resp.ok:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return [data]
        except requests.RequestException as exc:
            logger.debug("bpmn_to_json sidecar failed: %s", exc)
        return []

    def load_api_keys(self) -> Dict[str, str]:
        """
        Load cloud API keys from env file or JSON config.

        Returns:
            Dict of provider -> key (values never logged).
        """
        if config.BPMN_ASSISTANT_API_KEYS_JSON:
            try:
                data = json.loads(config.BPMN_ASSISTANT_API_KEYS_JSON)
                if isinstance(data, dict):
                    return {k: str(v) for k, v in data.items() if v}
            except json.JSONDecodeError:
                logger.warning("Invalid BPMN_ASSISTANT_API_KEYS_JSON")

        env_path = Path(config.BPMN_ASSISTANT_ENV_FILE)
        if not env_path.is_file():
            return {}

        keys: Dict[str, str] = {}
        try:
            text = env_path.read_text(encoding="utf-8", errors="replace")
            for match in _ENV_KEY_RE.finditer(text):
                name = match.group(1)
                value = match.group(2).strip().strip('"').strip("'")
                if value and not value.startswith("your-"):
                    keys[name] = value
        except OSError as exc:
            logger.warning("Cannot read BPMN env file: %s", exc)
        return keys

    def modify(
        self,
        message_history: List[Dict[str, str]],
        process: Optional[Dict[str, Any]] = None,
        *,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create or edit BPMN via POST /modify.

        Args:
            message_history: List of {role, content} items.
            process: Existing process payload for revisions.
            model: Override LLM model id.

        Returns:
            Sidecar JSON with bpmn_xml and bpmn_json.

        Raises:
            BpmnAssistantError: On HTTP or configuration errors.
        """
        if not config.BPMN_ASSISTANT_ENABLED:
            raise BpmnAssistantError("BPMN sidecar disabled in config.")

        api_keys = self.load_api_keys()
        if not api_keys:
            raise BpmnAssistantError(
                "missing_api_keys: configure keys in sidecar .env or "
                "BPMN_ASSISTANT_API_KEYS_JSON"
            )

        payload: Dict[str, Any] = {
            "message_history": message_history,
            "model": model or config.BPMN_ASSISTANT_MODEL,
            "api_keys": api_keys,
        }
        if process is not None:
            payload["process"] = process

        try:
            resp = requests.post(
                f"{self.base_url}/modify",
                json=payload,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise BpmnAssistantError(f"Sidecar unreachable: {exc}") from exc

        if resp.status_code >= 400:
            raise BpmnAssistantError(
                f"Sidecar error {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        if not data.get("bpmn_xml"):
            raise BpmnAssistantError("Sidecar returned empty bpmn_xml")
        return data

    def determine_intent(self, message: str) -> Optional[str]:
        """Optional intent probe via sidecar."""
        if not self.health():
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/determine_intent",
                json={"message": message},
                timeout=min(self.timeout_s, 30),
            )
            if resp.ok:
                body = resp.json()
                return body.get("intent") or body.get("response")
        except requests.RequestException:
            return None
        return None
