"""Per-company detail crawling."""

from __future__ import annotations

import requests

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import Company
from bvb_scraper.parsers.html import parse_detail_page
from bvb_scraper.session import get_session

logger = get_logger(__name__)


def fetch_symbol_detail(session: requests.Session, symbol: str) -> Company:
    """Fetch and parse the detail page for one symbol.

    Never raises: on any HTTP/parse failure returns a ``Company`` with
    ``error`` set so a single bad symbol cannot abort the run.
    """
    session = session or get_session()
    url = settings.detail_url_tmpl.format(symbol=symbol)
    try:
        resp = session.get(url, timeout=settings.request_timeout)
        logger.debug("detail %s status=%s", symbol, resp.status_code)
        if resp.status_code != 200:
            return Company(symbol=symbol, error=f"HTTP {resp.status_code}")
    except requests.RequestException as exc:
        logger.warning("detail %s request failed: %s", symbol, exc)
        return Company(symbol=symbol, error=str(exc))
    return parse_detail_page(resp.text, symbol)
