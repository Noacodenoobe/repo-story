"""
Index education guides and system profile into KnowledgeStore for RAG.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from . import config
from .knowledge_base import AnalysisRecord
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient, get_client

logger = logging.getLogger(__name__)


class GuideIndexer:
    """Chunk and embed guides for global RAG search."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        client: Optional[OllamaClient] = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.client = client or get_client()

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Return embedding vector or None on failure."""
        if not text.strip():
            return None
        try:
            if not self.client.ping():
                return None
            vec = self.client.embed(text[:4000])
            return np.asarray(vec, dtype=np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding failed: %s", exc)
            return None

    def _add(
        self,
        guide_id: Optional[str],
        source_type: str,
        section: str,
        text: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        emb = self._embed(text)
        self.store.add_chunk(
            guide_id=guide_id,
            source_type=source_type,
            section=section,
            text=text,
            metadata=meta,
            embedding=emb,
            model=config.MODEL_EMBED,
        )

    def index_record(self, record: AnalysisRecord, json_path: str = "") -> int:
        """Index one analysis record; returns chunk count."""
        gid = record.id
        edu = record.education_pack or record.lesson_deck or {}
        title = str(edu.get("title") or record.url)
        self.store.upsert_guide(
            guide_id=gid,
            url=record.url,
            slug=record.slug,
            title=title,
            json_path=json_path,
            created_at=record.created_at,
        )
        self.store.delete_chunks_for_guide(gid)
        count = 0

        def add(section: str, text: str, stype: str = "guide") -> None:
            nonlocal count
            if text and len(text.strip()) > 20:
                self._add(gid, stype, section, text.strip(), {"title": title})
                count += 1

        add("essence", str(edu.get("essence", "")))
        ov = edu.get("overview") or {}
        for key in ("what", "why", "how_it_works", "limitations"):
            add(f"overview.{key}", str(ov.get(key, "")))
        for i, uc in enumerate(edu.get("use_cases") or []):
            add(
                f"use_case.{i}",
                f"{uc.get('title')}: {uc.get('scenario')} — {uc.get('benefit')}",
            )
        for fs in edu.get("flow_steps") or []:
            add(
                "flow",
                f"{fs.get('title')}: {fs.get('description')} {fs.get('tip', '')}",
            )
        for ht in edu.get("howto") or []:
            cmds = " | ".join(ht.get("commands") or [])
            add(
                "howto",
                f"Krok {ht.get('step')}: {ht.get('title')}. {ht.get('body')} Komendy: {cmds}",
            )
        mg = edu.get("modify_guide") or {}
        for item in (mg.get("easy") or []) + (mg.get("advanced") or []):
            add("modify", f"{item.get('title')}: {item.get('body')}")
        for slide in edu.get("story_slides") or []:
            add("story", f"{slide.get('title')}: {slide.get('body')}")
        if record.polish_report:
            add("technical", record.polish_report[:3000], "technical")

        logger.info("Indexed guide %s: %d chunks", gid, count)
        return count

    def index_system_profile(self, profile: Dict[str, Any], summary: str) -> int:
        """Index system profile as global chunks (guide_id NULL)."""
        self.store.save_system_profile(profile, summary)
        with self.store._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE guide_id IS NULL AND source_type = 'system'")
        count = 0
        self._add(None, "system", "summary", summary, {"type": "profile"})
        count += 1
        for key, val in _flatten_profile(profile):
            text = f"{key}: {val}"
            if len(text) > 30:
                self._add(None, "system", key, text[:2000], {"type": "profile"})
                count += 1
        logger.info("Indexed system profile: %d chunks", count)
        return count


def _flatten_profile(obj: Any, prefix: str = "") -> List[tuple[str, str]]:
    """Flatten nested profile dict for chunking."""
    items: List[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            items.extend(_flatten_profile(v, key))
    elif isinstance(obj, list):
        items.append((prefix, ", ".join(str(x) for x in obj[:20])))
    else:
        items.append((prefix, str(obj)))
    return items
