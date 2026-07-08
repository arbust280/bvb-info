"""Normalized SQLAlchemy 2.0 ORM schema.

Dialect-agnostic (works on both PostgreSQL and SQLite). One table per entity
per the design; ``daily_prices`` accumulates history keyed on (symbol, date).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(255))
    instrument_type: Mapped[str | None] = mapped_column(String(64))
    segment: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(64))
    total_shares: Mapped[float | None] = mapped_column(Float)
    nominal_value: Mapped[float | None] = mapped_column(Float)
    share_capital: Mapped[float | None] = mapped_column(Float)
    trade_start_date: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    shareholders: Mapped[list["Shareholder"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["FinancialMetric"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(16))


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_daily_price"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[date] = mapped_column(index=True)
    price: Mapped[float | None] = mapped_column(Float)
    var_pct: Mapped[float | None] = mapped_column(Float)
    open: Mapped[float | None] = mapped_column(Float)
    max: Mapped[float | None] = mapped_column(Float)
    min: Mapped[float | None] = mapped_column(Float)
    avg: Mapped[float | None] = mapped_column(Float)
    value_ron: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    trades: Mapped[float | None] = mapped_column(Float)
    market: Mapped[str | None] = mapped_column(String(64))
    last_time: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), default="trading")


class Index(Base):
    __tablename__ = "indices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class IndexConstituent(Base):
    __tablename__ = "index_constituents"
    __table_args__ = (
        UniqueConstraint("index_name", "symbol", name="uq_index_constituent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_name: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    shares_issued: Mapped[float | None] = mapped_column(Float)
    ref_price: Mapped[float | None] = mapped_column(Float)
    free_float_pct: Mapped[float | None] = mapped_column(Float)


class Shareholder(Base):
    __tablename__ = "shareholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    holder: Mapped[str] = mapped_column(String(255))
    shares: Mapped[float | None] = mapped_column(Float)
    pct: Mapped[float | None] = mapped_column(Float)
    company: Mapped["Company"] = relationship(back_populates="shareholders")


class FinancialMetric(Base):
    __tablename__ = "financial_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    as_of: Mapped[date] = mapped_column(index=True)
    market_cap: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    pbv: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    div_yield: Mapped[float | None] = mapped_column(Float)
    dividend: Mapped[float | None] = mapped_column(Float)
    reference_price: Mapped[float | None] = mapped_column(Float)
    company: Mapped["Company"] = relationship(back_populates="metrics")


class FinancialStatement(Base):
    """Line items from PDF/XLS filings (populated in Phase 2)."""

    __tablename__ = "financial_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str | None] = mapped_column(String(32))
    statement_type: Mapped[str | None] = mapped_column(String(64))
    line_item: Mapped[str | None] = mapped_column(String(255))
    value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    source_filing: Mapped[str | None] = mapped_column(Text)


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("symbol", "url", name="uq_filing"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[str | None] = mapped_column(String(32))
    type: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))


class Dividend(Base):
    __tablename__ = "dividends"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column(Float)
    yield_pct: Mapped[float | None] = mapped_column(Float)
    ex_date: Mapped[str | None] = mapped_column(String(32))
    pay_date: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(Text)


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)


class CrawlMetadata(Base):
    """Per-resource incremental-refresh bookkeeping."""

    __tablename__ = "crawl_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
