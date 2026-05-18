"""
Baza wiedzy o analizach (KB).

Każda analiza repozytorium jest zapisywana jako JSON w katalogu ``reports/``.
Moduł umożliwia:
- zapis kompletnego "raportu" jako rekord,
- listowanie wszystkich rekordów,
- pobranie konkretnego po id,
- proste wyszukiwanie po nazwie/URL,
- usuwanie.

Świadomie nie używamy SQLite ani innej bazy - jeden katalog z JSON-ami jest
łatwy do przejrzenia ręcznie, kopiowania i usunięcia (zgodnie z regulaminem).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

logger = logging.getLogger(__name__)


@dataclass
class AnalysisRecord:
    """Kompletny zapis analizy jednego repo."""

    id: str
    url: str
    slug: str
    created_at: float
    repo_info: Dict[str, Any] = field(default_factory=dict)
    static: Dict[str, Any] = field(default_factory=dict)
    llm: Dict[str, Any] = field(default_factory=dict)
    polish_report: str = ""
    diagrams: Dict[str, str] = field(default_factory=dict)  # nazwa -> mermaid
    lesson_deck: Dict[str, Any] = field(default_factory=dict)
    education_pack: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "slug": self.slug,
            "created_at": self.created_at,
            "created_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)),
            "repo_info": self.repo_info,
            "static": self.static,
            "llm": self.llm,
            "polish_report": self.polish_report,
            "diagrams": self.diagrams,
            "lesson_deck": self.lesson_deck,
            "education_pack": self.education_pack,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisRecord":
        """Rebuild record from stored JSON."""
        return cls(
            id=data["id"],
            url=data.get("url", ""),
            slug=data.get("slug", ""),
            created_at=data.get("created_at", 0.0),
            repo_info=data.get("repo_info", {}),
            static=data.get("static", {}),
            llm=data.get("llm", {}),
            polish_report=data.get("polish_report", ""),
            diagrams=data.get("diagrams", {}),
            lesson_deck=data.get("lesson_deck", {}),
            education_pack=data.get("education_pack", {}),
        )


class KnowledgeBase:
    """Plikowa baza wiedzy w ``reports/``."""

    def __init__(self, base_dir: Path = config.REPORTS_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------- I/O
    def _path(self, record_id: str) -> Path:
        # Sanityzacja - id ma być UUID, ale na wszelki wypadek
        safe = "".join(c for c in record_id if c.isalnum() or c in "-_")
        return self.base_dir / f"{safe}.json"

    def save(self, record: AnalysisRecord) -> Path:
        path = self._path(record.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Zapisano raport: %s", path)
        return path

    def load(self, record_id: str) -> Optional[AnalysisRecord]:
        path = self._path(record_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AnalysisRecord(
            id=data["id"],
            url=data.get("url", ""),
            slug=data.get("slug", ""),
            created_at=data.get("created_at", 0.0),
            repo_info=data.get("repo_info", {}),
            static=data.get("static", {}),
            llm=data.get("llm", {}),
            polish_report=data.get("polish_report", ""),
            diagrams=data.get("diagrams", {}),
            lesson_deck=data.get("lesson_deck", {}),
            education_pack=data.get("education_pack", {}),
        )

    def delete(self, record_id: str) -> bool:
        path = self._path(record_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # --------------------------------------------------------- listing
    def list_records(self) -> List[Dict[str, Any]]:
        """Lekka lista rekordów (bez pełnych treści)."""
        items: List[Dict[str, Any]] = []
        for p in sorted(self.base_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # noqa: BLE001
                logger.warning("Pomijam uszkodzony plik %s: %s", p, e)
                continue
            edu = data.get("education_pack") or data.get("lesson_deck") or {}
            items.append({
                "id": data.get("id"),
                "url": data.get("url"),
                "slug": data.get("slug"),
                "created_at": data.get("created_at"),
                "created_at_iso": data.get("created_at_iso"),
                "presentation_title": edu.get("title"),
                "summary": {
                    "total_files": data.get("static", {}).get("total_files"),
                    "total_lines": data.get("static", {}).get("total_lines"),
                    "languages": list(data.get("static", {}).get("languages", {}).keys())[:5],
                    "frameworks": data.get("static", {}).get("frameworks", []),
                },
            })
        return items

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Bardzo proste filtrowanie po url/slug."""
        q = (query or "").lower().strip()
        if not q:
            return self.list_records()
        return [
            r for r in self.list_records()
            if q in (r.get("url") or "").lower() or q in (r.get("slug") or "").lower()
        ]

    # --------------------------------------------------------- factories
    @staticmethod
    def new_record(url: str, slug: str) -> AnalysisRecord:
        return AnalysisRecord(
            id=str(uuid.uuid4()),
            url=url,
            slug=slug,
            created_at=time.time(),
        )
