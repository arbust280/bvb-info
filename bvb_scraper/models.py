"""Typed domain models (Pydantic v2).

These replace the loose dictionaries used by the proof-of-concept. Every
crawler returns typed models; the repository persists them.
"""

from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Symbol(_Base):
    """A tradable instrument identifier from the discovery endpoint."""

    symbol: str
    isin: str | None = None
    name: str | None = None
    status: str | None = None  # T=tradable, D=delisted


class PriceSnapshot(_Base):
    """One trading-day price row for a symbol."""

    symbol: str
    date: date_type
    price: float | None = None
    var_pct: float | None = None
    open: float | None = None
    max: float | None = None
    min: float | None = None
    avg: float | None = None
    value_ron: float | None = None
    volume: float | None = None
    trades: float | None = None
    market: str | None = None
    last_time: str | None = None
    source: str = "trading"  # 'trading' | 'etf'


class Shareholder(_Base):
    """A single line of a company's shareholding structure."""

    holder: str
    shares: float | None = None
    pct: float | None = None


class News(_Base):
    """A news / current-report item shown on the detail page."""

    symbol: str | None = None
    date: str | None = None
    title: str | None = None
    url: str | None = None


class FinancialMetrics(_Base):
    """Valuation metrics extracted from the detail page (canonical names)."""

    symbol: str
    market_cap: float | None = None
    pe_ratio: float | None = None
    pbv: float | None = None
    eps: float | None = None
    div_yield: float | None = None
    dividend: float | None = None
    reference_price: float | None = None
    last_price: float | None = None


class Company(_Base):
    """Full company detail assembled from the detail page."""

    symbol: str
    isin: str | None = None
    name: str | None = None
    instrument_type: str | None = None
    segment: str | None = None
    category: str | None = None
    status: str | None = None
    # Valuation
    market_cap: float | None = None
    pe_ratio: float | None = None
    pbv: float | None = None
    eps: float | None = None
    div_yield: float | None = None
    dividend: float | None = None
    reference_price: float | None = None
    last_price: float | None = None
    # Share capital
    total_shares: float | None = None
    nominal_value: float | None = None
    share_capital: float | None = None
    trade_start_date: str | None = None
    # Nested
    shareholders: list[Shareholder] = Field(default_factory=list)
    news: list[News] = Field(default_factory=list)
    error: str | None = None


class IndexComponent(_Base):
    """A constituent of a BVB index (e.g. BET)."""

    index: str
    symbol: str
    company: str | None = None
    shares_issued: float | None = None
    ref_price: float | None = None
    free_float_pct: float | None = None


class Filing(_Base):
    """A current report / filing linked from BVB."""

    symbol: str
    date: str | None = None
    type: str | None = None
    title: str | None = None
    url: str | None = None
    local_path: str | None = None
    sha256: str | None = None


class Dividend(_Base):
    """A dividend event (placeholder-populated for now)."""

    symbol: str
    year: int | None = None
    amount: float | None = None
    yield_pct: float | None = None
    ex_date: str | None = None
    pay_date: str | None = None
    source_url: str | None = None
