"""
Structured deployment plan builder from RAG howto chunks (Phase C0).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .chat_grounding import extract_commands_from_context, is_meta_system_question


class DeploymentStep(BaseModel):
    """One installation step derived from guide howto."""

    order: int
    title: str
    body: str
    paths: List[str] = Field(default_factory=list)
    commands: List[str] = Field(default_factory=list)
    source_section: str = ""


class DeploymentPlan(BaseModel):
    """Structured install plan for a focused guide on the user's host."""

    visibility: Dict[str, Any] = Field(default_factory=dict)
    project: Dict[str, Any] = Field(default_factory=dict)
    host_rules: List[str] = Field(default_factory=list)
    recommended_paths: Dict[str, str] = Field(default_factory=dict)
    steps: List[DeploymentStep] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)


_STEP_RE = re.compile(
    r"Krok\s+(\d+)\s*:\s*([^\n]+)\n?(.*?)(?=Krok\s+\d+\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_PATH_RE = re.compile(r"(/mnt/ollama[/\w.-]*)")
_CMD_INLINE_RE = re.compile(r"Komendy:\s*([^\n]+)", re.IGNORECASE)


def _extract_paths(text: str) -> List[str]:
    return list(dict.fromkeys(_PATH_RE.findall(text)))


def _parse_howto_steps(text: str, section: str) -> List[DeploymentStep]:
    """Parse numbered howto steps from chunk text."""
    steps: List[DeploymentStep] = []
    for match in _STEP_RE.finditer(text):
        order = int(match.group(1))
        title = match.group(2).strip()
        body_raw = (match.group(3) or "").strip()
        body_lines = [ln.strip() for ln in body_raw.splitlines() if ln.strip()]
        body = " ".join(body_lines[:6])[:800]
        chunk_slice = text[match.start(): match.end()]
        cmds = extract_commands_from_context([chunk_slice])
        cmd_match = _CMD_INLINE_RE.search(body_raw)
        if cmd_match:
            for part in re.split(r"\s*\|\s*", cmd_match.group(1)):
                c = part.strip()
                if c and c not in cmds:
                    cmds.append(c)
        paths = _extract_paths(body_raw)
        steps.append(
            DeploymentStep(
                order=order,
                title=title,
                body=body or title,
                paths=paths,
                commands=cmds,
                source_section=section,
            )
        )
    return steps


def build_deployment_plan(
    message: str,
    citations: List[Dict[str, Any]],
    context_parts: List[str],
    *,
    focus_guide_title: Optional[str] = None,
    focus_guide_slug: Optional[str] = None,
    confidence: float = 0.0,
) -> DeploymentPlan:
    """
    Build a deterministic deployment plan from retrieved chunks.

    Args:
        message: User question (for visibility block).
        citations: RAG citation metadata.
        context_parts: Raw context strings passed to the LLM.
        focus_guide_title: Detected guide title if any.
        focus_guide_slug: Guide slug fragment if known.
        confidence: Focus detection confidence proxy (0–1).

    Returns:
        DeploymentPlan ready for JSON serialization.
    """
    paired = list(zip(citations, context_parts))
    howto_parts = [
        (c.get("section") or "", p)
        for c, p in paired
        if (c.get("section") or "").lower().startswith("howto")
        or "howto" in (p or "").lower()[:40]
    ]
    if not howto_parts:
        howto_parts = [
            (c.get("section") or "", p)
            for c, p in paired
            if c.get("guide_id") and "git clone" in (p or "").lower()
        ]

    steps: List[DeploymentStep] = []
    seen_orders: set[int] = set()
    for section, part in howto_parts:
        for step in _parse_howto_steps(part, section):
            if step.order not in seen_orders:
                seen_orders.add(step.order)
                steps.append(step)
    steps.sort(key=lambda s: s.order)

    rules_lines: List[str] = []
    indexed_sources: List[str] = []
    for c, part in paired:
        label = f"{c.get('guide_title', '?')} / {c.get('section', '?')}"
        indexed_sources.append(label)
        if (c.get("source_type") or "") == "rules" or "regulamin" in part.lower()[:80]:
            for line in part.splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "1.", "2.")) or "/mnt/ollama" in line:
                    rules_lines.append(line.lstrip("-* ").strip())

    all_paths = _extract_paths("\n".join(context_parts))
    recommended = {
        "clone_root": "/mnt/ollama/projekty/",
        "venv_root": "/mnt/ollama/ai-envs/",
    }
    for path in all_paths:
        if "projekty" in path and path.endswith("/"):
            recommended["clone_root"] = path
        elif "ai-envs" in path:
            recommended["venv_root"] = path

    gaps: List[str] = []
    if focus_guide_title and not steps:
        gaps.append(
            f"Brak sekcji howto w kontekście dla „{focus_guide_title}” — "
            "wygeneruj przewodnik w zakładce Nowy lub przeindeksuj bazę."
        )

    visibility = {
        "live_disk_access": False,
        "indexed_sources": list(dict.fromkeys(indexed_sources))[:12],
        "meta_question": is_meta_system_question(message),
        "summary_pl": (
            "Nie przeglądam całego dysku na żywo — korzystam ze zindeksowanych "
            "przewodników, profilu systemu i regulaminu hosta."
        ),
    }

    return DeploymentPlan(
        visibility=visibility,
        project={
            "guide_title": focus_guide_title or "",
            "guide_slug": focus_guide_slug or "",
            "confidence": round(confidence, 3),
        },
        host_rules=list(dict.fromkeys(rules_lines))[:10],
        recommended_paths=recommended,
        steps=steps,
        gaps=gaps,
        citations=citations,
    )


def deployment_plan_summary_pl(plan: DeploymentPlan) -> str:
    """Short Polish narrative for chat answers."""
    lines: List[str] = []
    if plan.visibility.get("meta_question"):
        lines.append(plan.visibility.get("summary_pl", ""))

    if plan.project.get("guide_title"):
        lines.append(f"Projekt: {plan.project['guide_title']}.")

    if plan.steps:
        lines.append("Kroki instalacji (z przewodnika):")
        for step in plan.steps[:8]:
            cmd_hint = ""
            if step.commands:
                cmd_hint = f" Komenda: `{step.commands[0]}`"
            lines.append(f"{step.order}. {step.title}.{cmd_hint}")
    elif plan.gaps:
        lines.extend(plan.gaps)

    if plan.recommended_paths:
        lines.append(
            "Zalecane ścieżki: projekty → "
            f"{plan.recommended_paths.get('clone_root', '/mnt/ollama/projekty/')}"
        )

    return "\n".join(lines).strip()
