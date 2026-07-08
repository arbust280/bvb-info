"""Symbol discovery via the autocomplete endpoint.

POST /proxyshld.aspx/GetInstrumentsList returns at most 10 matches per
search text, so we brute-force every A-Z and 0-9 prefix and deduplicate.
This endpoint returns JSON directly (preferred over HTML scraping).
"""

from __future__ import annotations

import json
import time

import requests

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import Symbol
from bvb_scraper.session import get_session

logger = get_logger(__name__)

_PREFIXES = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [
    chr(c) for c in range(ord("0"), ord("9") + 1)
]


def discover_all_symbols(session: requests.Session | None = None) -> list[Symbol]:
    """Enumerate all instruments known to the autocomplete endpoint."""
    session = session or get_session()
    seen: dict[str, Symbol] = {}

    for prefix in _PREFIXES:
        payload = json.dumps({"searchtext": prefix})
        try:
            resp = session.post(
                settings.discovery_url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=settings.request_timeout,
            )
            logger.debug("discover prefix=%s status=%s", prefix, resp.status_code)
            if resp.status_code != 200:
                continue
            items = resp.json().get("d", []) or []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("discover prefix=%s failed: %s", prefix, exc)
            continue

        for item in items:
            sym = (item.get("Symbol") or "").strip()
            if sym and sym not in seen:
                seen[sym] = Symbol(
                    symbol=sym,
                    isin=(item.get("Isin") or "").strip() or None,
                    name=(item.get("Name") or "").strip() or None,
                    status=(item.get("Status") or "").strip() or None,
                )
        time.sleep(settings.request_delay)

    symbols = sorted(seen.values(), key=lambda s: s.symbol)
    logger.info("Discovered %d symbols via autocomplete endpoint", len(symbols))
    return symbols
