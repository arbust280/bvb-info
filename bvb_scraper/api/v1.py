"""Versioned read-only JSON endpoints (``/api/v1``)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, String, desc, func, or_, select
from sqlalchemy.orm import Session

from bvb_scraper.api import schemas
from bvb_scraper.api.db import get_db
from bvb_scraper.db.schema import (
    Company,
    DailyPrice,
    FinancialMetric,
    Index,
    IndexConstituent,
    News,
    Shareholder,
)

router = APIRouter()

_MAX_LIMIT = 500


def _paginate(db: Session, stmt: Select, limit: int, offset: int) -> tuple[int, list]:
    """Run a list statement with a total count and limit/offset applied."""
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return total, list(rows)


# News dates are stored as scraped strings (``DD.MM.YYYY H:MM:SS``); rearrange
# to YYYYMMDD so string ordering is chronological on both Postgres and SQLite.
_NEWS_DATE_KEY = (
    func.substr(News.date, 7, 4, type_=String)
    + func.substr(News.date, 4, 2, type_=String)
    + func.substr(News.date, 1, 2, type_=String)
)


@router.get("", response_model=schemas.ApiStatus, include_in_schema=False)
@router.get("/", response_model=schemas.ApiStatus)
def api_status(db: Session = Depends(get_db)) -> schemas.ApiStatus:
    """Dataset overview: row counts, freshness, available indices."""
    return schemas.ApiStatus(
        name="BVB Info — free Bucharest Stock Exchange data API",
        docs="/api/docs",
        data_as_of=db.execute(select(func.max(DailyPrice.date))).scalar(),
        companies=db.execute(select(func.count(Company.id))).scalar_one(),
        price_rows=db.execute(select(func.count(DailyPrice.id))).scalar_one(),
        news_items=db.execute(select(func.count(News.id))).scalar_one(),
        indices=list(db.execute(select(Index.name).order_by(Index.name)).scalars()),
    )


@router.get("/companies", response_model=schemas.CompanyPage)
def list_companies(
    search: str | None = Query(None, description="Match symbol or name (case-insensitive)"),
    segment: str | None = None,
    category: str | None = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.CompanyPage:
    stmt = select(Company).order_by(Company.symbol)
    if search:
        needle = f"%{search}%"
        stmt = stmt.where(or_(Company.symbol.ilike(needle), Company.name.ilike(needle)))
    if segment:
        stmt = stmt.where(Company.segment == segment)
    if category:
        stmt = stmt.where(Company.category == category)
    total, items = _paginate(db, stmt, limit, offset)
    return schemas.CompanyPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/companies/{symbol}", response_model=schemas.CompanyDetail)
def get_company(symbol: str, db: Session = Depends(get_db)) -> schemas.CompanyDetail:
    symbol = symbol.upper()
    company = db.execute(select(Company).where(Company.symbol == symbol)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    detail = schemas.CompanyDetail.model_validate(company)
    detail.latest_metrics = db.execute(
        select(FinancialMetric)
        .where(FinancialMetric.company_id == company.id)
        .order_by(desc(FinancialMetric.as_of))
        .limit(1)
    ).scalar_one_or_none()
    detail.shareholders = [
        schemas.ShareholderOut.model_validate(s)
        for s in db.execute(
            select(Shareholder)
            .where(Shareholder.company_id == company.id)
            .order_by(desc(Shareholder.pct))
        ).scalars()
    ]
    detail.latest_price = db.execute(
        select(DailyPrice)
        .where(DailyPrice.symbol == symbol)
        .order_by(desc(DailyPrice.date))
        .limit(1)
    ).scalar_one_or_none()
    detail.news = [
        schemas.NewsOut.model_validate(n)
        for n in db.execute(
            select(News)
            .where(News.symbol == symbol)
            .order_by(desc(_NEWS_DATE_KEY), desc(News.id))
            .limit(20)
        ).scalars()
    ]
    return detail


@router.get("/prices", response_model=schemas.PricePage)
def list_prices(
    symbol: str | None = None,
    date_from: datetime.date | None = Query(None, description="Inclusive lower bound"),
    date_to: datetime.date | None = Query(None, description="Inclusive upper bound"),
    limit: int = Query(200, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.PricePage:
    stmt = select(DailyPrice).order_by(desc(DailyPrice.date), DailyPrice.symbol)
    if symbol:
        stmt = stmt.where(DailyPrice.symbol == symbol.upper())
    if date_from:
        stmt = stmt.where(DailyPrice.date >= date_from)
    if date_to:
        stmt = stmt.where(DailyPrice.date <= date_to)
    total, items = _paginate(db, stmt, limit, offset)
    return schemas.PricePage(total=total, limit=limit, offset=offset, items=items)


@router.get("/indices", response_model=list[str])
def list_indices(db: Session = Depends(get_db)) -> list[str]:
    return list(db.execute(select(Index.name).order_by(Index.name)).scalars())


@router.get("/indices/{name}", response_model=schemas.IndexDetail)
def get_index(name: str, db: Session = Depends(get_db)) -> schemas.IndexDetail:
    name = name.upper()
    constituents = list(
        db.execute(
            select(IndexConstituent)
            .where(IndexConstituent.index_name == name)
            .order_by(IndexConstituent.symbol)
        ).scalars()
    )
    if not constituents:
        raise HTTPException(status_code=404, detail=f"Unknown index: {name}")
    return schemas.IndexDetail(
        name=name,
        constituents=[schemas.ConstituentOut.model_validate(c) for c in constituents],
    )


@router.get("/news", response_model=schemas.NewsPage)
def list_news(
    symbol: str | None = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.NewsPage:
    stmt = select(News).order_by(desc(_NEWS_DATE_KEY), desc(News.id))
    if symbol:
        stmt = stmt.where(News.symbol == symbol.upper())
    total, items = _paginate(db, stmt, limit, offset)
    return schemas.NewsPage(total=total, limit=limit, offset=offset, items=items)
