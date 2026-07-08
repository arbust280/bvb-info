"""Tests for the BeautifulSoup detail-page parser."""

from pathlib import Path

import pytest

from bvb_scraper.models import Company
from bvb_scraper.parsers.html import parse_detail_page

FIXTURE = Path(__file__).parent / "fixtures" / "detail_sample.html"


@pytest.fixture(scope="module")
def company() -> Company:
    return parse_detail_page(FIXTURE.read_text(encoding="utf-8"), "TLV")


def test_symbol_set(company):
    assert company.symbol == "TLV"


def test_identity_fields(company):
    assert company.isin == "ROTLVAACNOR1"
    assert company.instrument_type == "Actiuni"
    assert company.segment == "Principal"
    assert company.category == "Premium"


def test_valuation_fields(company):
    assert company.market_cap == 43416630999.5
    assert company.pe_ratio == 9.32
    assert company.pbv == 1.86
    assert company.eps == 4.27
    assert company.div_yield == 3.22


def test_share_capital_fields(company):
    assert company.total_shares == 1090322225.0
    assert company.nominal_value == 10.0
    assert company.share_capital == 10903222250.0


def test_shareholders_parsed(company):
    assert len(company.shareholders) >= 1
    first = company.shareholders[0]
    assert first.holder == "Pers. Juridice Rezidenti"
    assert first.pct == 54.9239
    assert first.shares == 598847469.0
    # TOTAL row is excluded
    assert all(s.holder.lower() != "total" for s in company.shareholders)


def test_news_parsed(company):
    assert len(company.news) == 2
    assert company.news[0].url == "/info/report1.pdf"
    assert company.news[0].title == "Raport curent"


def test_empty_html_no_exception():
    c = parse_detail_page("", "XYZ")
    assert c.symbol == "XYZ"
    assert c.market_cap is None


def test_news_date_is_clean(company):
    # The news date must be a clean date token, not merged row text.
    import re

    for item in company.news:
        if item.date:
            assert re.fullmatch(
                r"\d{2}\.\d{2}\.\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?", item.date
            ), item.date
            assert len(item.date) <= 32
