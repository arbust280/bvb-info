"""Command-line entry point.

Thin dispatcher over the pipeline facade. Every subcommand is a small wrapper
so the same logic is reusable from cron/Celery/RQ.
"""

from __future__ import annotations

import argparse
import json

from bvb_scraper.config import settings
from bvb_scraper.db.base import init_db
from bvb_scraper.etl import pipeline
from bvb_scraper.logging_config import setup_logging


def _cmd_update_all(args: argparse.Namespace) -> None:
    summary = pipeline.update_all(
        max_workers=args.workers,
        export_path=args.export,
        with_details=not args.no_details,
        with_filings=args.with_filings,
    )
    print(json.dumps(summary["meta"], indent=2, default=str))


def _cmd_prices(_: argparse.Namespace) -> None:
    from bvb_scraper.db.base import get_sessionmaker
    from bvb_scraper.db.repository import Repository

    init_db()
    with get_sessionmaker()() as s:
        prices = pipeline.download_prices(repo=Repository(s))
    print(f"{len(prices)} price rows persisted")


def _cmd_company(args: argparse.Namespace) -> None:
    company = pipeline.update_company(args.symbol)
    print(company.model_dump_json(indent=2))


def _cmd_filings(args: argparse.Namespace) -> None:
    from bvb_scraper.db.base import get_sessionmaker
    from bvb_scraper.db.repository import Repository

    init_db()
    with get_sessionmaker()() as s:
        filings = pipeline.download_filings(args.symbol, repo=Repository(s))
    print(f"{len(filings)} filings for {args.symbol}")


def _cmd_init_db(_: argparse.Namespace) -> None:
    init_db()
    print("Database initialised")


def _cmd_discover(_: argparse.Namespace) -> None:
    from bvb_scraper.crawler.discover import discover_all_symbols

    symbols = discover_all_symbols()
    print(f"{len(symbols)} symbols discovered")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bvb_scraper", description="BVB ETL pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("update-all", help="Full ETL run")
    p_all.add_argument("--workers", type=int, default=None)
    p_all.add_argument("--export", type=str, default=None, help="Write JSON to PATH")
    p_all.add_argument("--with-filings", action="store_true")
    p_all.add_argument("--no-details", action="store_true")
    p_all.set_defaults(func=_cmd_update_all)

    sub.add_parser("prices", help="Fetch + persist price snapshots").set_defaults(func=_cmd_prices)

    p_co = sub.add_parser("company", help="Fetch + persist one company")
    p_co.add_argument("symbol")
    p_co.set_defaults(func=_cmd_company)

    p_fi = sub.add_parser("filings", help="Download filings for a symbol")
    p_fi.add_argument("symbol")
    p_fi.set_defaults(func=_cmd_filings)

    sub.add_parser("init-db", help="Create database tables").set_defaults(func=_cmd_init_db)
    sub.add_parser("discover", help="Discover all symbols").set_defaults(func=_cmd_discover)
    return parser


def main(argv: list[str] | None = None) -> None:
    setup_logging(settings.log_level)
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
