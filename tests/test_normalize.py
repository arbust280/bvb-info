"""Tests for Romanian->canonical normalization."""

from bvb_scraper.etl.normalize import normalize_label, normalize_metrics


def test_normalize_label_market_cap():
    assert normalize_label("Capitalizare") == "market_cap"


def test_normalize_label_strips_colon():
    assert normalize_label("ISIN:") == "isin"


def test_normalize_label_unknown():
    assert normalize_label("Necunoscut") is None


def test_normalize_metrics_values():
    m = normalize_metrics({"Capitalizare": "1.000,00", "PER": "12,5"}, "TLV")
    assert m.symbol == "TLV"
    assert m.market_cap == 1000.0
    assert m.pe_ratio == 12.5


def test_normalize_metrics_percent():
    m = normalize_metrics({"DIVY": "3,22"}, "TLV")
    assert m.div_yield == 3.22
