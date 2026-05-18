"""
One-shot migration: index existing JSON reports into SQLite knowledge base.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import config
from .guide_indexer import GuideIndexer
from .knowledge_base import AnalysisRecord, KnowledgeBase

logger = logging.getLogger(__name__)


def migrate_all(reports_dir: Path | None = None) -> int:
    """Index all reports in directory. Returns count of guides processed."""
    reports_dir = reports_dir or config.REPORTS_DIR
    indexer = GuideIndexer()
    kb = KnowledgeBase(base_dir=reports_dir)
    count = 0
    for path in sorted(reports_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            record = AnalysisRecord.from_dict(data)
            indexer.index_record(record, json_path=str(path))
            count += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip %s: %s", path.name, exc)
    logger.info("Migrated %d guides", count)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_all()
