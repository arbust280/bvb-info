"""Pipeline facade — the clean internal API.

Pure, scheduler-friendly functions (callable unchanged from cron/Celery/RQ).
No giant procedural main(): ``main.py`` is a thin CLI over these functions.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import requests

from bvb_scraper.config import settings
from bvb_scraper.crawler.companies import fetch_symbol_detail
from bvb_scraper.crawler.discover import discover_all_symbols
from bvb_scraper.crawler.filings import download_filing, fetch_current_reports
from bvb_scraper.crawler.indices import fetch_index_components
from bvb_scraper.crawler.prices import fetch_etf_snapshot, fetch_trading_snapshot
from bvb_scraper.db.base import get_sessionmaker, init_db
from bvb_scraper.db.repository import Repository
from bvb_scraper.export import export_json
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import Company, Filing, PriceSnapshot
from bvb_scraper.parsers import pdf as pdf_parser
from bvb_scraper.parsers import xlsx as xlsx_parser
from bvb_scraper.session import get_session

logger = get_logger(__name__)

_DOC_PARSERS = {
    ".pdf": pdf_parser.extract_financials,
    ".xls": xlsx_parser.extract_financials,
    ".xlsx": xlsx_parser.extract_financials,
}


def _repo_session():
    init_db()
    return get_sessionmaker()()


def download_prices(
    session: requests.Session | None = None, repo: Repository | None = None
) -> list[PriceSnapshot]:
    """Fetch trading + ETF snapshots and persist them (if a repo is given)."""
    session = session or get_session()
    prices = fetch_trading_snapshot(session) + fetch_etf_snapshot(session)
    if repo is not None:
        repo.upsert_prices(prices)
    return prices


def get_company(symbol: str, session: requests.Session | None = None) -> Company:
    """Fetch one company's detail without persisting (read-only helper)."""
    session = session or get_session()
    return fetch_symbol_detail(session, symbol)


def update_company(
    symbol: str,
    session: requests.Session | None = None,
    repo: Repository | None = None,
) -> Company:
    """Fetch and persist one company. Creates its own repo if none supplied."""
    session = session or get_session()
    owns_repo = repo is None
    db_session = None
    if owns_repo:
        db_session = _repo_session()
        repo = Repository(db_session)
    try:
        company = fetch_symbol_detail(session, symbol)
        if company.error is None:
            repo.upsert_company(company)
        return company
    finally:
        if owns_repo and db_session is not None:
            db_session.close()


def download_filings(
    symbol: str,
    session: requests.Session | None = None,
    repo: Repository | None = None,
    parse_documents: bool = True,
) -> list[Filing]:
    """Discover, download and (Phase 2) parse filings for a symbol."""
    session = session or get_session()
    filings = fetch_current_reports(session, symbol)
    downloaded = [download_filing(session, f, settings.storage_dir) for f in filings]
    if parse_documents:
        for f in downloaded:
            if not f.local_path:
                continue
            ext = os.path.splitext(f.local_path)[1].lower()
            parser = _DOC_PARSERS.get(ext)
            if parser is not None:
                parser(f.local_path)  # Phase 2: results logged, not yet persisted
    if repo is not None:
        repo.upsert_filings(downloaded)
    return downloaded


def update_all(
    max_workers: int | None = None,
    export_path: str | None = None,
    with_details: bool = True,
    with_filings: bool = False,
) -> dict:
    """Full ETL run: discover -> prices -> indices -> per-symbol details.

    Persists everything to the database and optionally writes a JSON export.
    One failing symbol never aborts the run.
    """
    max_workers = max_workers or settings.max_workers
    session = get_session()
    db_session = _repo_session()
    repo = Repository(db_session)

    summary: dict = {
        "meta": {
            "date": date.today().isoformat(),
            "generated_at": datetime.now().isoformat(),
            "source": "https://www.bvb.ro/ (reverse-engineered)",
        }
    }

    try:
        symbols = discover_all_symbols(session)
        repo.upsert_symbols(symbols)

        prices = download_prices(session, repo)
        components = fetch_index_components(session, "BET")
        repo.upsert_index_components(components)

        summary["meta"]["symbols_discovered"] = len(symbols)
        summary["meta"]["price_rows"] = len(prices)
        summary["meta"]["bet_components"] = len(components)

        companies: dict[str, dict] = {}
        if with_details:
            price_symbols = sorted({p.symbol for p in prices} | {s.symbol for s in symbols})
            logger.info("Enriching %d symbols (workers=%d)", len(price_symbols), max_workers)
            companies = _enrich_symbols(price_symbols, max_workers, repo, with_filings)
        summary["meta"]["companies_ok"] = sum(
            1 for c in companies.values() if not c.get("error")
        )
        summary["companies"] = companies
        summary["prices"] = [p.model_dump(mode="json") for p in prices]
        summary["index_components"] = {"BET": [c.model_dump() for c in components]}

        if export_path:
            export_json(summary, export_path)
        return summary
    finally:
        db_session.close()


def _enrich_symbols(
    symbols: list[str], max_workers: int, repo: Repository, with_filings: bool
) -> dict[str, dict]:
    """Fetch details for many symbols in parallel with thread-local sessions.

    Each worker uses its own session (via ``get_session()``), and per-symbol
    failures are caught and recorded so the run continues.
    """
    results: dict[str, dict] = {}

    def _work(sym: str) -> Company:
        worker_session = get_session()  # thread-local: one session per worker
        try:
            return fetch_symbol_detail(worker_session, sym)
        except Exception as exc:  # defensive belt-and-braces
            logger.warning("enrich %s crashed: %s", sym, exc)
            return Company(symbol=sym, error=str(exc))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_work, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            company = fut.result()
            results[sym] = company.model_dump(mode="json")
            if company.error is None:
                try:
                    repo.upsert_company(company)
                    if with_filings:
                        download_filings(sym, repo=repo)
                except Exception as exc:
                    logger.warning("persist %s failed: %s", sym, exc)
    return results
