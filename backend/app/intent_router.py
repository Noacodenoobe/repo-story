"""
Chat intent routing for response modes (Phase C).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .chat_grounding import is_meta_system_question

_PROCESS_DESIGN_PATTERNS = (
    r"\bdiagram\b.*\b(bpmn|proces)",
    r"\b(bpmn|proces)\b.*\bdiagram",
    r"\bzaprojektuj\b.*\bproces",
    r"\bstw[oó]rz\b.*\b(diagram|proces|bpmn)",
    r"\bworkflow\b",
    r"\bprocess design\b",
    r"\bmodel\b.*\bproces",
)

_DEPLOYMENT_PATTERNS = (
    r"\binstal",
    r"\bclone\b",
    r"\bdocker",
    r"\bhowto\b",
    r"\bsciezk",
    r"\bścieżk",
    r"\bfolder",
    r"\bkatalog",
    r"\bwdroż",
    r"\bdeploy",
    r"\bczy widzisz",
    r"\bdost[eę]p do plik",
    r"\bassistent",
    r"\basystent",
    r"\bbpmn-assist",
    r"\bbpm-assist",
)


def _normalize(text: str) -> str:
    """Lowercase and strip Polish diacritics for matching."""
    t = text.lower()
    for a, b in (("ą", "a"), ("ć", "c"), ("ę", "e"), ("ł", "l"), ("ń", "n"),
                 ("ó", "o"), ("ś", "s"), ("ź", "z"), ("ż", "z")):
        t = t.replace(a, b)
    return t


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def detect_response_mode(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    *,
    sidecar_healthy: bool = False,
) -> str:
    """
    Pick chat response mode: default, deployment, or process_design.

    Priority: process_design > deployment > default.

    Args:
        message: Current user message.
        history: Recent chat turns for context.
        sidecar_healthy: When True, process_design may be chosen more readily.

    Returns:
        One of ``default``, ``deployment``, ``process_design``.
    """
    history = history or []
    combined = _normalize(message)
    for msg in history[-4:]:
        if msg.get("role") == "user":
            combined += " " + _normalize((msg.get("content") or "")[:400])

    if _matches_any(combined, _PROCESS_DESIGN_PATTERNS):
        return "process_design"

    design_hints = ("bpmn", "proces biznes", "diagram procesu", "workflow")
    if sidecar_healthy and any(h in combined for h in design_hints):
        if not _matches_any(combined, (r"\binstal", r"\bclone", r"\basystent.*instal")):
            return "process_design"

    if (
        _matches_any(combined, _DEPLOYMENT_PATTERNS)
        or is_meta_system_question(message)
    ):
        return "deployment"

    return "default"
