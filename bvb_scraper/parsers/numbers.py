"""Romanian number parsing.

BVB renders numbers in Romanian locale: '.' groups thousands and ',' is the
decimal separator (e.g. ``1.090.322,25`` -> ``1090322.25``).
"""

from __future__ import annotations

import re

# Matches a pure Romanian thousands-grouped integer, e.g. '598.847.469'.
_THOUSANDS_GROUPED = re.compile(r"\d{1,3}(\.\d{3})+$")


def ro_float(value: object) -> float | None:
    """Convert a Romanian-formatted numeric string to ``float``.

    Handles thousands separators ('.'), decimal comma (','), currency
    suffixes ('lei'/'RON') and common dash placeholders. A value containing
    only dots is treated as a thousands-grouped integer *only* when it matches
    the grouping pattern (so a genuine decimal like ``39.82`` is preserved).
    Returns ``None`` when the value is missing or unparseable.

    >>> ro_float("1.090.322,25")
    1090322.25
    >>> ro_float("598.847.469")
    598847469.0
    >>> ro_float("39.82")
    39.82
    >>> ro_float("-") is None
    True
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "—", "N/A", "n/a"):
        return None
    s = s.replace("\xa0", " ").replace(" lei", "").replace(" RON", "").strip()
    s = s.replace(" ", "")
    if "." in s and "," in s:
        # Both present: '.' = thousands, ',' = decimal.
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Only comma: decimal separator.
        s = s.replace(",", ".")
    elif "." in s and _THOUSANDS_GROUPED.match(s):
        # Only dots, in grouping pattern: thousands separators.
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def ro_pct(value: object) -> float | None:
    """Convert a Romanian percentage string to a float value in percent.

    Strips '%', sign markers and trend arrows before parsing.

    >>> ro_pct("+0,52%")
    0.52
    >>> ro_pct("-") is None
    True
    """
    if value is None:
        return None
    s = str(value).replace("%", "").replace("+", "").replace("▲", "").replace("▼", "").strip()
    return ro_float(s)
