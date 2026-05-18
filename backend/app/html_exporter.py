"""
Export analysis records as standalone HTML guides.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config
from .knowledge_base import AnalysisRecord

logger = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_EXPORTS_DIR = config.REPORTS_DIR / "exports"


class HtmlExporter:
    """Render offline HTML from AnalysisRecord."""

    def __init__(self) -> None:
        _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def export(self, record: AnalysisRecord) -> Path:
        """Write HTML file and return path."""
        edu = record.education_pack or record.lesson_deck or {}
        template = self.env.get_template("guide_export.html")
        html = template.render(
            title=edu.get("title") or "Przewodnik",
            url=record.url,
            essence=edu.get("essence", ""),
            summary_3=edu.get("summary_3") or [],
            overview=edu.get("overview") or {},
            use_cases=edu.get("use_cases") or [],
            flow_steps=edu.get("flow_steps") or [],
            flow_mermaid=edu.get("flow_mermaid", ""),
            install_flow_mermaid=edu.get("install_flow_mermaid", ""),
            howto=edu.get("howto") or [],
            modify_guide=edu.get("modify_guide") or {},
            story_slides=edu.get("story_slides") or edu.get("slides") or [],
            quiz=edu.get("quiz") or [],
            charts_json=json.dumps(edu.get("charts") or {}, ensure_ascii=False),
            static_json=json.dumps(record.static or {}, ensure_ascii=False),
        )
        out = _EXPORTS_DIR / f"{record.id}.html"
        out.write_text(html, encoding="utf-8")
        logger.info("Exported HTML: %s", out)
        return out

    def get_path(self, record_id: str) -> Optional[Path]:
        """Return export path if exists."""
        p = _EXPORTS_DIR / f"{record_id}.html"
        return p if p.is_file() else None
