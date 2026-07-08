"""HTML parsing of BVB company detail pages using BeautifulSoup.

Replaces the proof-of-concept's regex parsing. Selectors are anchored on
stable element IDs (``gvDetails`` shareholders grid, ``gv5News`` news) and on
the site-wide ``<td>label</td><td>value</td>`` row convention, so they survive
minor layout changes.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from bvb_scraper.etl.normalize import RO_TO_CANONICAL, normalize_label, normalize_value
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import Company, News, Shareholder
from bvb_scraper.parsers.numbers import ro_float, ro_pct

logger = get_logger(__name__)

# Leading Romanian date (optionally with time) in a news row.
_NEWS_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?")

# Canonical fields that Company accepts directly from label/value rows.
_COMPANY_FIELDS = set(Company.model_fields)


def _iter_label_value_rows(soup: BeautifulSoup):
    """Yield ``(label, value)`` for every two-cell ``<tr>`` in the document."""
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False) or tr.find_all("td")
        if len(cells) == 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if label:
                yield label, value


def _parse_shareholders(soup: BeautifulSoup) -> list[Shareholder]:
    """Extract the shareholding structure from the ``#gvDetails`` grid."""
    table = soup.find(id="gvDetails")
    if table is None:
        return []
    holders: list[Shareholder] = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        if cells[0].lower() in ("actionar", "total"):
            continue
        holders.append(
            Shareholder(holder=cells[0], shares=ro_float(cells[1]), pct=ro_pct(cells[2]))
        )
    return holders


def _parse_news(soup: BeautifulSoup, symbol: str) -> list[News]:
    """Extract news items from the ``#gv5News`` grid (best-effort)."""
    table = soup.find(id="gv5News")
    if table is None:
        return []
    items: list[News] = []
    for tr in table.find_all("tr"):
        text = tr.get_text(" ", strip=True)
        if not text:
            continue
        link = tr.find("a", href=True)
        match = _NEWS_DATE_RE.search(text)
        date = match.group(0) if match else None
        url = link["href"] if link is not None else None
        title = link.get_text(" ", strip=True) if link is not None else None
        if not title:
            # Fall back to the row text minus the date token.
            title = _NEWS_DATE_RE.sub("", text).strip() or None
        items.append(News(symbol=symbol, date=date, title=title, url=url))
    return items


def _parse_name(soup: BeautifulSoup, symbol: str) -> str | None:
    """Extract the issuer name from the page <title>.

    Titles look like ``'BVB - Actiuni TLV BANCA TRANSILVANIA S.A.'``; the name
    is whatever follows the ticker symbol.
    """
    if soup.title is None:
        return None
    title = soup.title.get_text(" ", strip=True)
    match = re.search(rf"\b{re.escape(symbol)}\b\s+(.+)$", title)
    return match.group(1).strip() or None if match else None


def parse_detail_page(html: str, symbol: str) -> Company:
    """Parse a FinancialInstrumentsDetails page into a :class:`Company`.

    Never raises for malformed input: on failure it returns a ``Company`` with
    ``error`` set so the pipeline can continue.
    """
    data: dict[str, object] = {"symbol": symbol}
    try:
        soup = BeautifulSoup(html or "", "lxml")
        for label, value in _iter_label_value_rows(soup):
            field = normalize_label(label)
            if field and field in _COMPANY_FIELDS:
                data[field] = normalize_value(field, value)
        if "name" not in data or not data.get("name"):
            data["name"] = _parse_name(soup, symbol)
        shareholders = _parse_shareholders(soup)
        news = _parse_news(soup, symbol)
        return Company(**data, shareholders=shareholders, news=news)
    except Exception as exc:  # defensive: one bad page must not abort a run
        logger.warning("Failed to parse detail page for %s: %s", symbol, exc)
        return Company(symbol=symbol, error=str(exc))
