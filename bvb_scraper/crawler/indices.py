"""Index constituents (BET and others) from IndicesProfiles."""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import IndexComponent
from bvb_scraper.parsers.numbers import ro_float, ro_pct
from bvb_scraper.session import get_session

logger = get_logger(__name__)


def fetch_index_components(
    session: requests.Session | None = None, index: str = "BET"
) -> list[IndexComponent]:
    """Fetch the constituents table for a BVB index (default BET)."""
    session = session or get_session()
    try:
        resp = session.get(settings.indices_url, timeout=settings.request_timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("index components fetch failed: %s", exc)
        return []

    try:
        tables = pd.read_html(StringIO(resp.text), flavor="lxml")
    except Exception:
        tables = []

    for df in tables:
        if "Simbol" in list(df.columns):
            records: list[IndexComponent] = []
            for _, row in df.iterrows():
                symbol = str(row.get("Simbol", "")).strip()
                if not symbol or symbol.lower() == "nan":
                    continue
                records.append(
                    IndexComponent(
                        index=index,
                        symbol=symbol,
                        company=str(row.get("Societate", "")).strip() or None,
                        shares_issued=ro_float(row.get("Actiuni")),
                        ref_price=ro_float(row.get("Pret ref.")),
                        free_float_pct=ro_pct(row.get("FF")),
                    )
                )
            logger.info("index %s: %d components", index, len(records))
            return records
    logger.warning("index %s: no components table found", index)
    return []
