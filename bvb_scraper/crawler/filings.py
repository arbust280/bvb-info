"""Current reports / filings discovery and download.

Uses the real ``SelectedData/CurrentReports`` endpoint discovered during
reverse-engineering. Downloaded files are content-hashed so unchanged files
are not re-downloaded (incremental).
"""

from __future__ import annotations

import hashlib
import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import Filing
from bvb_scraper.session import get_session

logger = get_logger(__name__)


def fetch_current_reports(session: requests.Session, symbol: str) -> list[Filing]:
    """Discover current reports/filings for a symbol.

    Parses the CurrentReports page for a table of dated report links. Tolerant
    of layout: returns whatever dated anchor rows it can find.
    """
    session = session or get_session()
    url = f"{settings.current_reports_url}?s={symbol}"
    try:
        resp = session.get(url, timeout=settings.request_timeout)
        if resp.status_code != 200:
            return []
    except requests.RequestException as exc:
        logger.warning("filings %s fetch failed: %s", symbol, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    filings: list[Filing] = []
    for tr in soup.find_all("tr"):
        link = tr.find("a", href=True)
        if link is None:
            continue
        href = link["href"]
        # Only treat document links as filings.
        if not any(
            href.lower().endswith(ext) for ext in (".pdf", ".xls", ".xlsx", ".doc", ".docx")
        ):
            continue
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        date_txt = cells[0] if cells else None
        filings.append(
            Filing(
                symbol=symbol,
                date=date_txt,
                title=link.get_text(" ", strip=True) or None,
                url=urljoin(settings.base_url, href),
            )
        )
    logger.info("filings %s: %d documents", symbol, len(filings))
    return filings


def download_filing(
    session: requests.Session, filing: Filing, storage_dir: str | None = None
) -> Filing:
    """Download a filing to local storage, hashing content for incrementality.

    If a file with the same content hash already exists, the download is
    skipped. Returns the filing with ``local_path`` and ``sha256`` populated.
    """
    session = session or get_session()
    storage_dir = storage_dir or settings.storage_dir
    if not filing.url:
        return filing

    dest_dir = os.path.join(storage_dir, filing.symbol)
    os.makedirs(dest_dir, exist_ok=True)
    filename = os.path.basename(filing.url.split("?")[0]) or "filing"
    local_path = os.path.join(dest_dir, filename)

    try:
        resp = session.get(filing.url, timeout=settings.request_timeout, stream=True)
        resp.raise_for_status()
        content = resp.content
    except requests.RequestException as exc:
        logger.warning("download %s failed: %s", filing.url, exc)
        return filing

    sha256 = hashlib.sha256(content).hexdigest()
    if os.path.exists(local_path):
        with open(local_path, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() == sha256:
                logger.debug("filing unchanged, skipping write: %s", local_path)
                return filing.model_copy(update={"local_path": local_path, "sha256": sha256})

    with open(local_path, "wb") as fh:
        fh.write(content)
    logger.info("downloaded filing -> %s", local_path)
    return filing.model_copy(update={"local_path": local_path, "sha256": sha256})
