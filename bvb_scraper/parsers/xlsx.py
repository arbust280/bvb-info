"""XLS/XLSX financial-statement parsing (Phase 2 skeleton).

Opens the spreadsheet and returns a per-sheet preview. Canonical mapping is
Phase 2 work and is logged, not silently skipped.
"""

from __future__ import annotations

from bvb_scraper.logging_config import get_logger

logger = get_logger(__name__)


def extract_financials(path: str) -> list[dict]:
    """Extract raw sheet data from an XLS/XLSX filing.

    Returns a list of ``{"sheet": str, "columns": list, "rows": list[dict]}``.
    Canonical line-item mapping is not yet implemented (Phase 2).
    """
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        logger.warning("pandas not installed; cannot parse %s", path)
        return []

    sheets: list[dict] = []
    try:
        book = pd.read_excel(path, sheet_name=None)
    except Exception as exc:
        logger.warning("Failed to read spreadsheet %s: %s", path, exc)
        return []

    for name, df in book.items():
        sheets.append(
            {
                "sheet": name,
                "columns": [str(c) for c in df.columns],
                "rows": df.head(50).to_dict(orient="records"),
            }
        )
    logger.info(
        "XLS %s: read %d sheets; financial-figure extraction not yet "
        "implemented (Phase 2)",
        path,
        len(sheets),
    )
    return sheets
