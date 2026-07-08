"""Tests for the Romanian number parser."""

from bvb_scraper.parsers.numbers import ro_float, ro_pct


def test_ro_float_grouped_decimal():
    assert ro_float("1.090.322,25") == 1090322.25


def test_ro_float_small_decimal():
    assert ro_float("0,20") == 0.2


def test_ro_float_large_number():
    assert ro_float("43.416.630.999,50") == 43416630999.5


def test_ro_float_plain_integer():
    assert ro_float("1234") == 1234.0


def test_ro_float_dash_is_none():
    assert ro_float("-") is None


def test_ro_float_none_is_none():
    assert ro_float(None) is None


def test_ro_float_currency_suffix():
    assert ro_float("12 lei") == 12.0


def test_ro_pct_signed_percent():
    assert ro_pct("+0,52%") == 0.52


def test_ro_pct_arrow():
    assert ro_pct("▲1,3%") == 1.3


def test_ro_pct_dash_is_none():
    assert ro_pct("-") is None


def test_ro_float_thousands_grouped_integer():
    assert ro_float("598.847.469") == 598847469.0


def test_ro_float_billions_grouped_integer():
    assert ro_float("1.090.322.225") == 1090322225.0


def test_ro_float_decimal_dot_preserved():
    # A genuine 2-digit decimal must not be mangled into thousands.
    assert ro_float("39.82") == 39.82
