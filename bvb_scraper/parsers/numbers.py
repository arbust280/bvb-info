"""Romanian number parsing.

BVB renders numbers in Romanian locale: '.' groups thousands and ',' is the
decimal separator (e.g. ``1.090.322,25`` -> ``1090322.25``).
"""

from __future__ import annotations


def ro_float(value: object) -> float | None:
    """Convert a Romanian-formatted numeric string to ``float``.

    Handles thousands separators ('.'), decimal comma (','), currency
    suffixes ('lei'/'RON') and common dash placeholders. Returns ``None``
    when the value is missing or unparseable.

    >>> ro_float("1.090.322,25")
    1090322.25
    >>> ro_float("0,20")
    0.2
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
    s = (
        str(value)
        .replace("%", "")
        .replace("+", "")
        .replace("▲", "")
        .replace("▼", "")
        .strip()
    )
    return ro_float(s)
