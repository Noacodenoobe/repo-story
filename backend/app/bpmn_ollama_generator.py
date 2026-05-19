"""
Local BPMN 2.0 XML generation via Ollama (Phase C5 — no cloud API keys).
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional, Tuple

from . import config
from .llm_client import OllamaClient, OllamaError, get_client

logger = logging.getLogger(__name__)

_XML_BLOCK_RE = re.compile(r"```(?:xml|bpmn)?\s*\n([\s\S]*?)```", re.IGNORECASE)
_DEFINITIONS_RE = re.compile(
    r"(<\?xml[\s\S]*?<(?:bpmn2?:|bpmn:)definitions[\s\S]*?</(?:bpmn2?:|bpmn:)definitions>)",
    re.IGNORECASE,
)

_SYSTEM = (
    "You output valid BPMN 2.0 XML only. "
    "Use bpmn2 namespace http://www.omg.org/spec/BPMN/20100524/MODEL. "
    "Include one executable process with start event, tasks, end event, sequence flows. "
    "Use Polish labels for tasks when the user writes in Polish. "
    "No markdown outside the XML. No explanation."
)


def _extract_xml(raw: str) -> str:
    """Pull BPMN XML from model output."""
    text = (raw or "").strip()
    for match in _XML_BLOCK_RE.finditer(text):
        candidate = match.group(1).strip()
        if "definitions" in candidate.lower():
            return candidate
    match = _DEFINITIONS_RE.search(text)
    if match:
        return match.group(1).strip()
    if "<definitions" in text.lower():
        start = text.lower().find("<?xml")
        if start < 0:
            start = text.lower().find("<bpmn")
        if start < 0:
            start = text.lower().find("<definitions")
        if start >= 0:
            return text[start:].strip()
    return ""


def _ensure_process_ids(xml: str, process_name: str) -> str:
    """Ensure minimal id attributes if model omitted them."""
    if 'id="Process_' not in xml and 'id="Process' not in xml:
        pid = f"Process_{uuid.uuid4().hex[:8]}"
        xml = xml.replace(
            "<bpmn2:process ",
            f'<bpmn2:process id="{pid}" name="{process_name[:80]}" ',
            1,
        )
    return xml


def generate_bpmn_xml_ollama(
    user_prompt: str,
    *,
    existing_xml: Optional[str] = None,
    client: Optional[OllamaClient] = None,
    model: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Generate or revise BPMN XML using a local Ollama model.

    Args:
        user_prompt: Process description in natural language.
        existing_xml: Previous BPMN XML when revising.
        client: Ollama client override.
        model: Model name override.

    Returns:
        Tuple of (bpmn_xml, model_used).

    Raises:
        OllamaError: When Ollama is offline or generation fails.
    """
    llm = client or get_client()
    model_name = model or config.BPMN_OLLAMA_MODEL

    if not llm.ping():
        raise OllamaError("Ollama niedostępna.")
    if not llm.has_model(model_name):
        raise OllamaError(f"Brak modelu lokalnego: {model_name}")

    if existing_xml:
        prompt = (
            f"Revise this BPMN 2.0 XML according to the user request.\n"
            f"USER REQUEST:\n{user_prompt}\n\n"
            f"CURRENT XML:\n{existing_xml[:12000]}\n\n"
            "Return the full updated XML document only."
        )
    else:
        prompt = (
            f"Create BPMN 2.0 XML for this business process:\n{user_prompt}\n\n"
            "Return one complete XML document with bpmn2:definitions, "
            "one bpmn2:process, startEvent, tasks, endEvent, sequenceFlow elements."
        )

    result = llm.generate(
        prompt=prompt,
        model=model_name,
        system=_SYSTEM,
        temperature=0.15,
    )
    xml = _extract_xml(result.response or "")
    if not xml or "definitions" not in xml.lower():
        raise OllamaError("Model nie zwrócił poprawnego BPMN XML.")

    if not xml.lstrip().startswith("<?xml"):
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml

    xml = _ensure_process_ids(xml, user_prompt[:60])
    return xml, model_name
