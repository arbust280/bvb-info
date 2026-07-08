"""PDF financial-statement parsing (Phase 2 skeleton).

The interface is real and wired into the pipeline: it opens the PDF and
returns any detected tables' raw rows. Mapping those rows to canonical
financial line items (Revenue, EBIT, EBITDA, Net Income, Assets, ...) is
Phase 2 work and is logged rather than silently returning nothing.
"""

from __future__ import annotations

from bvb_scraper.logging_config import get_logger

logger = get_logger(__name__)


def extract_financials(path: str) -> list[dict]:
    """Extract raw tables from a PDF filing.

    Returns a list of ``{"page": int, "rows": list[list[str]]}`` dicts.
    Canonical line-item mapping is not yet implemented (Phase 2).
    """
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        logger.warning("pdfplumber not installed; cannot parse %s", path)
        return []

    tables: list[dict] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                for tbl in page.extract_tables() or []:
                    tables.append({"page": page_no, "rows": tbl})
    except Exception as exc:
        logger.warning("Failed to read PDF %s: %s", path, exc)
        return []

    logger.info(
        "PDF %s: extracted %d raw tables; financial-figure extraction not yet "
        "implemented (Phase 2)",
        path,
        len(tables),
    )
    return tables
