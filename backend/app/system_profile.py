"""
Collect and manage local system profile for personalized recommendations.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from . import config
from .guide_indexer import GuideIndexer
from .knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

_SCRIPT = config.PROJECT_ROOT / "scripts" / "collect-system-profile.sh"


class SystemProfileService:
    """Run profile script and persist results."""

    def __init__(self, store: Optional[KnowledgeStore] = None) -> None:
        self.store = store or KnowledgeStore()
        self.indexer = GuideIndexer(store=self.store)

    def collect_via_script(self, timeout: int = 60) -> Dict[str, Any]:
        """Execute collect-system-profile.sh and return parsed JSON."""
        if not _SCRIPT.is_file():
            raise FileNotFoundError(f"Brak skryptu: {_SCRIPT}")
        result = subprocess.run(
            ["/usr/bin/env", "bash", str(_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(config.PROJECT_ROOT),
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Skrypt profilu zakończył się kodem {result.returncode}: "
                f"{result.stderr[:500]}"
            )
        stdout = result.stdout.strip()
        profile = json.loads(stdout)
        out_path = config.DATA_DIR / "system-profile.json"
        out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return profile

    def build_summary(self, profile: Dict[str, Any]) -> str:
        """Short text summary for RAG and prompts."""
        parts = []
        host = profile.get("host") or {}
        if host.get("hostname"):
            parts.append(f"Host: {host['hostname']}")
        if host.get("os"):
            parts.append(f"System: {host['os']}")
        gpu = profile.get("gpu") or []
        if gpu:
            parts.append(f"GPU: {gpu[0].get('name', gpu[0]) if isinstance(gpu[0], dict) else gpu[0]}")
        tools = profile.get("tools") or {}
        found = [k for k, v in tools.items() if v and v != "not_found"]
        if found:
            parts.append(f"Narzędzia: {', '.join(found[:12])}")
        audio = profile.get("audio") or {}
        if audio.get("server"):
            parts.append(f"Audio: {audio['server']}")
        return ". ".join(parts) or json.dumps(profile, ensure_ascii=False)[:500]

    def refresh(self) -> Dict[str, Any]:
        """Collect, save, and re-index system profile."""
        from .host_rules import index_host_rules

        profile = self.collect_via_script()
        summary = self.build_summary(profile)
        chunk_count = self.indexer.index_system_profile(profile, summary)
        rules_result = index_host_rules(self.store)
        return {
            "collected_at": self.store.get_system_profile().get("collected_at"),
            "summary": summary,
            "chunks_indexed": chunk_count,
            "rules_indexed": rules_result.get("indexed", 0),
        }

    def upload(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Save manually uploaded profile JSON."""
        summary = self.build_summary(profile)
        out_path = config.DATA_DIR / "system-profile.json"
        out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        chunk_count = self.indexer.index_system_profile(profile, summary)
        return {"summary": summary, "chunks_indexed": chunk_count}

    def get(self) -> Optional[Dict[str, Any]]:
        """Return stored profile wrapper."""
        return self.store.get_system_profile()
