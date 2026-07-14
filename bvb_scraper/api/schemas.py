"""Pydantic response models for the public API.

These mirror the DB columns (``db/schema.py``), not the scraper's input
models: the API contract should not change when crawl internals do. All are
``from_attributes`` so routes can return ORM rows directly.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanySummary(ORMModel):
    symbol: str
    name: str | None = None
    isin: str | None = None
    instrument_type: str | None = None
    segment: str | None = None
    category: str | None = None
    status: str | None = None


class MetricsOut(ORMModel):
    as_of: datetime.date
    market_cap: float | None = None
    pe_ratio: float | None = None
    pbv: float | None = None
    eps: float | None = None
    div_yield: float | None = None
    dividend: float | None = None
    reference_price: float | None = None


class ShareholderOut(ORMModel):
    holder: str
    shares: float | None = None
    pct: float | None = None


class NewsOut(ORMModel):
    symbol: str
    date: str | None = None
    title: str | None = None
    url: str | None = None


class PriceOut(ORMModel):
    symbol: str
    date: datetime.date
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
    source: str


class CompanyDetail(CompanySummary):
    total_shares: float | None = None
    nominal_value: float | None = None
    share_capital: float | None = None
    trade_start_date: str | None = None
    latest_metrics: MetricsOut | None = None
    shareholders: list[ShareholderOut] = []
    latest_price: PriceOut | None = None
    news: list[NewsOut] = []


class ConstituentOut(ORMModel):
    index_name: str
    symbol: str
    company: str | None = None
    shares_issued: float | None = None
    ref_price: float | None = None
    free_float_pct: float | None = None


class IndexDetail(BaseModel):
    name: str
    constituents: list[ConstituentOut]


class Page(BaseModel):
    """Envelope for paginated list responses."""

    total: int
    limit: int
    offset: int
    items: list


class CompanyPage(Page):
    items: list[CompanySummary]


class PricePage(Page):
    items: list[PriceOut]


class NewsPage(Page):
    items: list[NewsOut]


class ApiStatus(BaseModel):
    """Dataset overview served at the API root."""

    name: str
    docs: str
    data_as_of: datetime.date | None
    companies: int
    price_rows: int
    news_items: int
    indices: list[str]
