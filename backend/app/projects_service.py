"""
Catalog of analyzed repositories (Phase B2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .knowledge_base import KnowledgeBase
from .knowledge_store import KnowledgeStore


class ProjectsService:
    """List analyzed repos with guide indexing status."""

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        store: Optional[KnowledgeStore] = None,
    ) -> None:
        self.kb = kb or KnowledgeBase()
        self.store = store or KnowledgeStore()

    def list_projects(self) -> List[Dict[str, Any]]:
        """
        Return merged view of JSON reports and SQLite guides.

        Returns:
            List of project dicts for API response.
        """
        indexed_ids: Set[str] = self.store.list_guide_ids()
        items: List[Dict[str, Any]] = []
        for rec in self.kb.list_records():
            report_id = rec.get("id") or ""
            edu_title = rec.get("presentation_title") or rec.get("slug") or rec.get("url")
            items.append({
                "slug": rec.get("slug"),
                "title": edu_title,
                "url": rec.get("url"),
                "report_id": report_id,
                "analyzed_at": rec.get("created_at"),
                "analyzed_at_iso": rec.get("created_at_iso"),
                "has_guide_in_kb": report_id in indexed_ids,
            })
        return items
