"""Server-rendered frontend: market overview + company detail pages."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from bvb_scraper.api.db import get_db
from bvb_scraper.api.v1 import _NEWS_DATE_KEY
from bvb_scraper.db.schema import (
    Company,
    DailyPrice,
    FinancialMetric,
    IndexConstituent,
    News,
    Shareholder,
)

router = APIRouter()

_BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))


def _fmt_num(value: float | None, decimals: int = 2) -> str:
    """Format numbers for the tables; em-dash for missing values."""
    if value is None:
        return "—"
    if decimals == 0 or float(value).is_integer() and abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


templates.env.filters["num"] = _fmt_num


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    as_of = db.execute(select(func.max(DailyPrice.date))).scalar()
    prices = list(
        db.execute(
            select(DailyPrice, Company.name)
            .join(Company, Company.symbol == DailyPrice.symbol, isouter=True)
            .where(DailyPrice.date == as_of)
            .order_by(desc(DailyPrice.value_ron))
        ).all()
    )
    constituents = list(
        db.execute(
            select(IndexConstituent)
            .where(IndexConstituent.index_name == "BET")
            .order_by(IndexConstituent.symbol)
        ).scalars()
    )
    stats = {
        "companies": db.execute(select(func.count(Company.id))).scalar_one(),
        "price_rows": db.execute(select(func.count(DailyPrice.id))).scalar_one(),
        "news_items": db.execute(select(func.count(News.id))).scalar_one(),
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {"as_of": as_of, "prices": prices, "constituents": constituents, "stats": stats},
    )


@router.get("/company/{symbol}", response_class=HTMLResponse)
def company_page(request: Request, symbol: str, db: Session = Depends(get_db)) -> HTMLResponse:
    symbol = symbol.upper()
    company = db.execute(select(Company).where(Company.symbol == symbol)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    latest_price = db.execute(
        select(DailyPrice)
        .where(DailyPrice.symbol == symbol)
        .order_by(desc(DailyPrice.date))
        .limit(1)
    ).scalar_one_or_none()
    metrics = db.execute(
        select(FinancialMetric)
        .where(FinancialMetric.company_id == company.id)
        .order_by(desc(FinancialMetric.as_of))
        .limit(1)
    ).scalar_one_or_none()
    shareholders = list(
        db.execute(
            select(Shareholder)
            .where(Shareholder.company_id == company.id)
            .order_by(desc(Shareholder.pct))
        ).scalars()
    )
    news = list(
        db.execute(
            select(News)
            .where(News.symbol == symbol)
            .order_by(desc(_NEWS_DATE_KEY), desc(News.id))
            .limit(25)
        ).scalars()
    )
    return templates.TemplateResponse(
        request,
        "company.html",
        {
            "c": company,
            "latest_price": latest_price,
            "metrics": metrics,
            "shareholders": shareholders,
            "news": news,
        },
    )
