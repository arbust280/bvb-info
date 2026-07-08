"""Persistence layer.

Dialect-agnostic upserts (select-then-insert/update) so the same code runs on
PostgreSQL and SQLite, plus incremental-refresh helpers backed by
``crawl_metadata``.
"""

from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from bvb_scraper.db import schema
from bvb_scraper.logging_config import get_logger
from bvb_scraper.models import (
    Company as CompanyModel,
    Filing as FilingModel,
    IndexComponent,
    PriceSnapshot,
    Symbol as SymbolModel,
)

logger = get_logger(__name__)


class Repository:
    """Upserts and incremental bookkeeping over a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── Symbols ──
    def upsert_symbols(self, symbols: list[SymbolModel]) -> int:
        for sym in symbols:
            row = self.session.scalar(
                select(schema.Symbol).where(schema.Symbol.symbol == sym.symbol)
            )
            if row is None:
                row = schema.Symbol(symbol=sym.symbol)
                self.session.add(row)
            row.isin, row.name, row.status = sym.isin, sym.name, sym.status
        self.session.commit()
        logger.info("upserted %d symbols", len(symbols))
        return len(symbols)

    # ── Prices ──
    def upsert_prices(self, prices: list[PriceSnapshot]) -> int:
        for p in prices:
            row = self.session.scalar(
                select(schema.DailyPrice).where(
                    schema.DailyPrice.symbol == p.symbol, schema.DailyPrice.date == p.date
                )
            )
            if row is None:
                row = schema.DailyPrice(symbol=p.symbol, date=p.date)
                self.session.add(row)
            for field in (
                "price", "var_pct", "open", "max", "min", "avg",
                "value_ron", "volume", "trades", "market", "last_time", "source",
            ):
                setattr(row, field, getattr(p, field))
        self.session.commit()
        logger.info("upserted %d daily prices", len(prices))
        return len(prices)

    # ── Company (+ nested shareholders, metrics, news) ──
    def upsert_company(self, company: CompanyModel) -> schema.Company:
        row = self.session.scalar(
            select(schema.Company).where(schema.Company.symbol == company.symbol)
        )
        if row is None:
            row = schema.Company(symbol=company.symbol)
            self.session.add(row)
        for field in (
            "isin", "name", "instrument_type", "segment", "category", "status",
            "total_shares", "nominal_value", "share_capital", "trade_start_date",
        ):
            setattr(row, field, getattr(company, field))
        self.session.flush()

        # Replace shareholders snapshot.
        row.shareholders.clear()
        for sh in company.shareholders:
            row.shareholders.append(
                schema.Shareholder(holder=sh.holder, shares=sh.shares, pct=sh.pct)
            )
        # Append a metrics snapshot for today.
        row.metrics.append(
            schema.FinancialMetric(
                as_of=date.today(),
                market_cap=company.market_cap,
                pe_ratio=company.pe_ratio,
                pbv=company.pbv,
                eps=company.eps,
                div_yield=company.div_yield,
                dividend=company.dividend,
                reference_price=company.reference_price,
            )
        )
        # News (dedupe by url per symbol).
        for n in company.news:
            if n.url and not self.session.scalar(
                select(schema.News).where(
                    schema.News.symbol == company.symbol, schema.News.url == n.url
                )
            ):
                self.session.add(
                    schema.News(symbol=company.symbol, date=n.date, title=n.title, url=n.url)
                )
        self.session.commit()
        return row

    # ── Index constituents ──
    def upsert_index_components(self, components: list[IndexComponent]) -> int:
        indices = {c.index for c in components}
        for name in indices:
            if not self.session.scalar(select(schema.Index).where(schema.Index.name == name)):
                self.session.add(schema.Index(name=name))
        for c in components:
            row = self.session.scalar(
                select(schema.IndexConstituent).where(
                    schema.IndexConstituent.index_name == c.index,
                    schema.IndexConstituent.symbol == c.symbol,
                )
            )
            if row is None:
                row = schema.IndexConstituent(index_name=c.index, symbol=c.symbol)
                self.session.add(row)
            row.company = c.company
            row.shares_issued = c.shares_issued
            row.ref_price = c.ref_price
            row.free_float_pct = c.free_float_pct
        self.session.commit()
        logger.info("upserted %d index constituents", len(components))
        return len(components)

    # ── Filings ──
    def upsert_filings(self, filings: list[FilingModel]) -> int:
        for f in filings:
            row = self.session.scalar(
                select(schema.Filing).where(
                    schema.Filing.symbol == f.symbol, schema.Filing.url == f.url
                )
            )
            if row is None:
                row = schema.Filing(symbol=f.symbol, url=f.url)
                self.session.add(row)
            row.date, row.type, row.title = f.date, f.type, f.title
            row.local_path, row.sha256 = f.local_path, f.sha256
        self.session.commit()
        logger.info("upserted %d filings", len(filings))
        return len(filings)

    # ── Incremental refresh helpers ──
    def should_refresh(
        self,
        resource_key: str,
        etag: str | None = None,
        last_modified: str | None = None,
        content_hash: str | None = None,
    ) -> bool:
        """Return True if a resource looks changed since the last crawl."""
        row = self.session.scalar(
            select(schema.CrawlMetadata).where(
                schema.CrawlMetadata.resource_key == resource_key
            )
        )
        if row is None:
            return True
        if etag and row.etag and etag == row.etag:
            return False
        if content_hash and row.content_hash and content_hash == row.content_hash:
            return False
        if last_modified and row.last_modified and last_modified == row.last_modified:
            return False
        return True

    def record_crawl(
        self,
        resource_key: str,
        etag: str | None = None,
        last_modified: str | None = None,
        content_hash: str | None = None,
    ) -> None:
        """Record the latest crawl signature for a resource."""
        row = self.session.scalar(
            select(schema.CrawlMetadata).where(
                schema.CrawlMetadata.resource_key == resource_key
            )
        )
        if row is None:
            row = schema.CrawlMetadata(resource_key=resource_key)
            self.session.add(row)
        row.etag = etag
        row.last_modified = last_modified
        row.content_hash = content_hash
        self.session.commit()

    @staticmethod
    def content_hash(data: bytes | str) -> str:
        """Compute a sha256 hex digest of response content."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).hexdigest()
