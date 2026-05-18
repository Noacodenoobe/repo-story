"""
Detect non-Polish user-facing text and optionally translate via local LLM.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from . import config
from .llm_client import OllamaClient, get_client

logger = logging.getLogger(__name__)

_POLISH_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
_EN_STOPWORDS = {
    "the", "and", "your", "with", "that", "this", "for", "from", "install",
    "installs", "creates", "users", "tool", "open", "source", "reduces",
    "unwanted", "noise", "virtual", "microphone", "recording", "calls",
    "typically", "acceptable", "e.g.", "e.g", "setup", "click",
}
_PL_HINTS = {
    "jest", "dla", "jak", "że", "oraz", "możesz", "program", "system",
    "mikrofon", "dźwięk", "krok", "instalacja", "uruchom", "projekt",
}


def looks_english(text: str) -> bool:
    """Heuristic: True if text is likely English rather than Polish."""
    if not text or len(text.strip()) < 8:
        return False
    lower = text.lower()
    words = re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", lower)
    if not words:
        return False
    pl_chars = sum(1 for c in text if c in _POLISH_CHARS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    pl_hits = sum(1 for w in words if w in _PL_HINTS)
    if pl_chars >= 2 or pl_hits >= 2:
        return False
    if en_hits >= 2:
        return True
    if pl_chars == 0 and len(words) >= 6 and en_hits >= 1:
        return True
    return False


def ensure_polish(
    text: str,
    client: Optional[OllamaClient] = None,
    context: str = "",
) -> str:
    """Return Polish text, translating via Bielik when heuristic detects English."""
    cleaned = (text or "").strip()
    if not cleaned or not looks_english(cleaned):
        return cleaned
    cli = client or get_client()
    if not cli.ping() or not cli.has_model(config.MODEL_POLISH):
        return cleaned
    prompt = (
        f"Przetłumacz na polski (prosty język, bez żargonu IT). Kontekst: {context or 'przewodnik'}.\n"
        f"Zwróć TYLKO przetłumaczony tekst, bez cudzysłowów.\n\n{cleaned}"
    )
    try:
        result = cli.generate(
            prompt=prompt,
            model=config.MODEL_POLISH,
            system="Jesteś tłumaczem. Odpowiadasz wyłącznie po polsku.",
        )
        out = (result.response or "").strip()
        return out if out else cleaned
    except Exception as exc:  # noqa: BLE001
        logger.warning("Polish translation failed: %s", exc)
        return cleaned


def ensure_polish_dict(
    data: Dict[str, Any],
    keys: List[str],
    client: Optional[OllamaClient] = None,
) -> Dict[str, Any]:
    """Translate top-level string fields in place."""
    for key in keys:
        if isinstance(data.get(key), str):
            data[key] = ensure_polish(data[key], client=client, context=key)
    return data


def polish_overview(overview: Dict[str, str], client: Optional[OllamaClient] = None) -> Dict[str, str]:
    """Ensure overview subfields are Polish."""
    out = dict(overview or {})
    for key in ("what", "why", "how_it_works", "limitations"):
        if out.get(key):
            out[key] = ensure_polish(str(out[key]), client=client, context=f"overview.{key}")
    return out


def polish_use_cases(
    cases: List[Dict[str, Any]],
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """Polish use case cards."""
    result = []
    for uc in cases or []:
        item = dict(uc)
        for field in ("title", "scenario", "benefit"):
            if item.get(field):
                item[field] = ensure_polish(str(item[field]), client=client, context="use_case")
        result.append(item)
    return result


def polish_flow_steps(
    steps: List[Dict[str, Any]],
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """Polish flow step texts."""
    result = []
    for step in steps or []:
        item = dict(step)
        for field in ("title", "description", "tip"):
            if item.get(field):
                item[field] = ensure_polish(str(item[field]), client=client, context="flow")
        result.append(item)
    return result


def polish_howto(
    steps: List[Dict[str, Any]],
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """Polish howto titles and bodies (not shell commands)."""
    result = []
    for step in steps or []:
        item = dict(step)
        for field in ("title", "body"):
            if item.get(field):
                item[field] = ensure_polish(str(item[field]), client=client, context="howto")
        result.append(item)
    return result
