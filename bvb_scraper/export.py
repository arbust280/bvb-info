"""JSON export for debugging / inspection (preserves POC output shape)."""

from __future__ import annotations

import json
import os

from bvb_scraper.logging_config import get_logger

logger = get_logger(__name__)


def export_json(payload: dict, path: str) -> None:
    """Write ``payload`` to ``path`` as pretty UTF-8 JSON."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    size_kb = os.path.getsize(path) // 1024
    logger.info("Exported JSON -> %s (%d KB)", path, size_kb)
