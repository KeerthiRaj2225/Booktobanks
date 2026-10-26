"""Low-level helpers: parsing Indian-format amounts and the many date styles banks use."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_NUM_DATE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$")
_MON_DATE = re.compile(r"^(\d{1,2})[\s\-/]?([A-Za-z]{3,4})[\s\-/,]*(\d{2}|\d{4})$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

_AMOUNT = re.compile(r"^\(?-?₹?\s*(?:\d{1,3}(?:,\d{2,3})*|\d+)(?:\.\d{1,2})?\)?(?:\s*\(?(?:cr|dr)\)?)?$", re.I)


def _year(y: str) -> int:
    yi = int(y)
    if len(y) == 2:
        yi += 2000 if yi < 70 else 1900
    return yi


def parse_date(text: str) -> Optional[date]:
    """Parse a date string like 01/04/24, 01-04-2024, 1 Apr 2024, 01-Apr-24, 2024-04-01."""
    if not text:
        return None
    t = text.strip().replace(",", " ")
    t = re.sub(r"\s+", " ", t)
    try:
        m = _NUM_DATE.match(t)
        if m:
            d, mo, y = m.groups()
            return date(_year(y), int(mo), int(d))
        m = _MON_DATE.match(t)
        if m:
            d, mon, y = m.groups()
            mo = MONTHS.get(mon.lower()[:4]) or MONTHS.get(mon.lower()[:3])
            if mo:
                return date(_year(y), mo, int(d))
        m = _ISO_DATE.match(t)
        if m:
            y, mo, d = m.groups()
            return date(int(y), int(mo), int(d))
    except ValueError:
        return None
    return None


def looks_like_amount(text: str) -> bool:
    t = text.strip()
    if not t or not any(c.isdigit() for c in t):
        return False
    # Must contain a decimal point or a comma grouping to count as money; bare integers are
    # usually reference numbers.
    core = re.sub(r"(?i)\s*\(?(cr|dr)\)?$", "", t)
    if "." not in core and "," not in core:
        return False
    return bool(_AMOUNT.match(t))


def parse_amount(text: str) -> Optional[float]:
    """'1,23,456.78' -> 123456.78 ; '500.00 Dr' -> -500.0 ; '(250.00)' -> -250.0"""
    if text is None:
        return None
    t = text.strip()
    if not t or t in {"-", "--", "0", "nil", "NIL"}:
        return 0.0 if t in {"0"} else None
    neg = False
    low = t.lower()
    if low.endswith("dr") or low.endswith("(dr)"):
        neg = True
    t = re.sub(r"(?i)\(?(cr|dr)\)?$", "", t).strip()
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    if t.startswith("-"):
        neg = True
        t = t[1:]
    t = t.replace("₹", "").replace(",", "").replace(" ", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def fmt_inr(v: float) -> str:
    """Indian digit grouping: 1234567.5 -> 12,34,567.50"""
    neg = v < 0
    v = abs(v)
    whole, frac = f"{v:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + "." + frac
