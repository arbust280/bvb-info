"""Normalization: Romanian BVB labels -> canonical English field names.

One canonical schema for the whole pipeline. All Romanian-specific naming is
confined to the ``RO_TO_CANONICAL`` map here.
"""

from __future__ import annotations

from bvb_scraper.models import FinancialMetrics
from bvb_scraper.parsers.numbers import ro_float, ro_pct

# Canonical field name for each Romanian label found on BVB detail pages.
RO_TO_CANONICAL: dict[str, str] = {
    # Identity
    "Simbol": "symbol",
    "ISIN": "isin",
    "Tip": "instrument_type",
    "Segment": "segment",
    "Categorie": "category",
    "Stare": "status",
    # Prices
    "Pret": "price",
    "Pret referinta": "reference_price",
    "Ultimul pret": "last_price",
    "Pret deschidere": "open",
    "Pret maxim": "day_max",
    "Pret minim": "day_min",
    "Pret mediu": "avg",
    "Var": "var_abs",
    "Var (%)": "var_pct",
    # Valuation
    "Capitalizare": "market_cap",
    "PER": "pe_ratio",
    "P/BV": "pbv",
    "EPS": "eps",
    "DIVY": "div_yield",
    # Share capital
    "Numar total actiuni": "total_shares",
    "Valoare Nominala": "nominal_value",
    "Capital social": "share_capital",
    "Data start tranzactionare": "trade_start_date",
}

# Which canonical fields are percentages (parsed with ro_pct) vs plain floats.
_PERCENT_FIELDS = {"div_yield", "var_pct"}
# Canonical fields that stay as strings (not numeric).
_STRING_FIELDS = {
    "symbol",
    "isin",
    "instrument_type",
    "segment",
    "category",
    "status",
    "trade_start_date",
}


def normalize_label(ro_label: str) -> str | None:
    """Map a Romanian label to its canonical field name (or ``None``)."""
    if ro_label is None:
        return None
    key = ro_label.strip().rstrip(":").strip()
    return RO_TO_CANONICAL.get(key)


def normalize_value(canonical_field: str, raw: object) -> object:
    """Coerce a raw string to the right type for a canonical field."""
    if canonical_field in _STRING_FIELDS:
        return None if raw is None else str(raw).strip() or None
    if canonical_field in _PERCENT_FIELDS:
        return ro_pct(raw)
    return ro_float(raw)


def normalize_metrics(raw: dict[str, object], symbol: str) -> FinancialMetrics:
    """Build :class:`FinancialMetrics` from a raw ``{ro_label: value}`` dict."""
    data: dict[str, object] = {"symbol": symbol}
    metric_fields = set(FinancialMetrics.model_fields)
    for ro_label, value in raw.items():
        field = normalize_label(ro_label)
        if field and field in metric_fields:
            data[field] = normalize_value(field, value)
    return FinancialMetrics(**data)
