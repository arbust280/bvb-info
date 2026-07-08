"""Trading-day price snapshots.

Preserves both the GET (all stocks) and POST/ASP.NET-postback (ETF tab)
flows against CurrentTradingDay. ASP.NET hidden fields are extracted with
BeautifulSoup (not regex).
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import PriceSnapshot
from bvb_scraper.parsers.numbers import ro_float, ro_pct
from bvb_scraper.session import get_session

logger = get_logger(__name__)

_HIDDEN_FIELDS = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")


def _read_tables(html: str) -> list[pd.DataFrame]:
    try:
        return pd.read_html(StringIO(html), flavor="lxml")
    except Exception:  # pragma: no cover - fallback parser
        try:
            return pd.read_html(StringIO(html))
        except Exception:
            return []


def _rows_from_snapshot(df: pd.DataFrame, source: str, today: date) -> list[PriceSnapshot]:
    rows: list[PriceSnapshot] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Simbol", "")).strip()
        if not symbol or symbol.lower() == "nan":
            continue
        rows.append(
            PriceSnapshot(
                symbol=symbol,
                date=today,
                price=ro_float(row.get("Pret")),
                var_pct=ro_pct(row.get("Var. (%)")),
                open=ro_float(row.get("Desch.")),
                max=ro_float(row.get("Max.")),
                min=ro_float(row.get("Min.")),
                avg=ro_float(row.get("Mediu")),
                value_ron=ro_float(row.get("Valoare")),
                volume=ro_float(row.get("Volum")),
                trades=ro_float(row.get("Nr. tranz.")),
                market=str(row.get("Piata", "")).strip() or None,
                last_time=str(row.get("Ora", "")).strip() or None,
                source=source,
            )
        )
    return rows


def fetch_trading_snapshot(session: requests.Session | None = None) -> list[PriceSnapshot]:
    """Fetch the live CurrentTradingDay snapshot for all stocks."""
    session = session or get_session()
    today = date.today()
    try:
        resp = session.get(settings.trading_url, timeout=settings.request_timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("trading snapshot fetch failed: %s", exc)
        return []

    for df in _read_tables(resp.text):
        cols = list(df.columns)
        if "Simbol" in cols and "Valoare" in cols:
            rows = _rows_from_snapshot(df, "trading", today)
            logger.info("trading snapshot: %d symbols", len(rows))
            return rows
    logger.warning("trading snapshot: no matching table found")
    return []


def _extract_hidden_fields(html: str) -> dict[str, str]:
    """Extract ASP.NET postback hidden fields using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    fields: dict[str, str] = {}
    for name in _HIDDEN_FIELDS:
        el = soup.find(id=name) or soup.find(attrs={"name": name})
        if el is not None and el.has_attr("value"):
            fields[name] = el["value"]
    return fields


def fetch_etf_snapshot(session: requests.Session | None = None) -> list[PriceSnapshot]:
    """Fetch the ETF / 'Unitati de fond' tab via ASP.NET postback."""
    session = session or get_session()
    today = date.today()
    try:
        get_resp = session.get(settings.trading_url, timeout=settings.request_timeout)
        fields = _extract_hidden_fields(get_resp.text)
        post_data = {
            "__EVENTTARGET": settings.etf_event_target,
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            **fields,
        }
        post_resp = session.post(
            settings.trading_url, data=post_data, timeout=settings.request_timeout
        )
    except requests.RequestException as exc:
        logger.error("ETF snapshot fetch failed: %s", exc)
        return []

    for df in _read_tables(post_resp.text):
        cols = list(df.columns)
        if "Simbol" in cols and "Valoare" in cols:
            rows: list[PriceSnapshot] = []
            for _, row in df.iterrows():
                symbol = str(row.get("Simbol", "")).strip()
                if not symbol or symbol.lower() == "nan":
                    continue
                rows.append(
                    PriceSnapshot(
                        symbol=symbol,
                        date=today,
                        price=ro_float(row.get("Pret")),
                        var_pct=ro_pct(row.get("Var. (%)")),
                        value_ron=ro_float(row.get("Valoare")),
                        source="etf",
                    )
                )
            logger.info("ETF snapshot: %d instruments", len(rows))
            return rows
    logger.warning("ETF snapshot: no matching table found")
    return []
