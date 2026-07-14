"""Public API endpoint tests against an in-memory SQLite fixture DB."""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bvb_scraper.api.app import create_app
from bvb_scraper.api.db import get_db
from bvb_scraper.db.schema import (
    Base,
    Company,
    DailyPrice,
    FinancialMetric,
    Index,
    IndexConstituent,
    News,
    Shareholder,
)

D = datetime.date(2026, 7, 9)


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        tlv = Company(symbol="TLV", name="Banca Transilvania", segment="Principal", isin="RO..")
        digi = Company(symbol="DIGI", name="Digi Communications N.V.", segment="Principal")
        s.add_all([tlv, digi])
        s.flush()
        s.add_all(
            [
                DailyPrice(symbol="TLV", date=D, price=39.86, var_pct=0.1, source="trading"),
                DailyPrice(
                    symbol="TLV",
                    date=D - datetime.timedelta(days=1),
                    price=39.5,
                    source="trading",
                ),
                DailyPrice(symbol="DIGI", date=D, price=57.0, source="trading"),
                FinancialMetric(company_id=tlv.id, as_of=D, market_cap=1.0, pe_ratio=12.0),
                Shareholder(company_id=tlv.id, holder="Free float", pct=70.0),
                Shareholder(company_id=tlv.id, holder="NN Group", pct=10.0),
                Index(name="BET"),
                IndexConstituent(index_name="BET", symbol="TLV", company="Banca Transilvania"),
                News(symbol="TLV", date="09.07.2026 14:00:00", title="new", url="u1"),
                News(symbol="TLV", date="29.06.2026 8:45:11", title="old", url="u2"),
            ]
        )
        s.commit()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: factory()
    return TestClient(app)


def test_status_root(client: TestClient) -> None:
    body = client.get("/api/v1/").json()
    assert body["companies"] == 2
    assert body["data_as_of"] == D.isoformat()
    assert body["indices"] == ["BET"]


def test_list_companies_and_search(client: TestClient) -> None:
    body = client.get("/api/v1/companies").json()
    assert body["total"] == 2
    assert [c["symbol"] for c in body["items"]] == ["DIGI", "TLV"]

    body = client.get("/api/v1/companies", params={"search": "transilvania"}).json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "TLV"


def test_company_detail(client: TestClient) -> None:
    body = client.get("/api/v1/companies/tlv").json()  # case-insensitive
    assert body["name"] == "Banca Transilvania"
    assert body["latest_metrics"]["pe_ratio"] == 12.0
    assert [s["holder"] for s in body["shareholders"]] == ["Free float", "NN Group"]
    assert body["latest_price"]["price"] == 39.86
    assert [n["title"] for n in body["news"]] == ["new", "old"]  # newest first


def test_company_404(client: TestClient) -> None:
    assert client.get("/api/v1/companies/NOPE").status_code == 404


def test_prices_filters(client: TestClient) -> None:
    body = client.get("/api/v1/prices").json()
    assert body["total"] == 3
    assert body["items"][0]["date"] == D.isoformat()  # newest first

    body = client.get(
        "/api/v1/prices", params={"symbol": "tlv", "date_from": D.isoformat()}
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["price"] == 39.86


def test_prices_pagination(client: TestClient) -> None:
    body = client.get("/api/v1/prices", params={"limit": 2, "offset": 2}).json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_indices(client: TestClient) -> None:
    assert client.get("/api/v1/indices").json() == ["BET"]
    body = client.get("/api/v1/indices/bet").json()
    assert body["constituents"][0]["symbol"] == "TLV"
    assert client.get("/api/v1/indices/XYZ").status_code == 404


def test_news_order_and_filter(client: TestClient) -> None:
    body = client.get("/api/v1/news", params={"symbol": "TLV"}).json()
    assert [n["title"] for n in body["items"]] == ["new", "old"]


def test_cache_header_on_success_only(client: TestClient) -> None:
    ok = client.get("/api/v1/companies")
    assert "s-maxage" in ok.headers["cache-control"]
    missing = client.get("/api/v1/companies/NOPE")
    assert "cache-control" not in missing.headers


def test_openapi_docs_exposed(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/v1/companies/{symbol}" in paths
