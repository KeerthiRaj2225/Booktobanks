"""Detect which bank a statement belongs to and pull header metadata (account no, IFSC, period)."""
from __future__ import annotations

import re
from typing import Optional

from .utils import parse_date

# (display name, text markers, IFSC prefix, default Tally ledger name)
BANKS = [
    ("HDFC Bank", ["HDFC BANK", "HDFCBANK"], "HDFC", "HDFC Bank A/c"),
    ("State Bank of India", ["STATE BANK OF INDIA", "SBI "], "SBIN", "SBI A/c"),
    ("ICICI Bank", ["ICICI BANK"], "ICIC", "ICICI Bank A/c"),
    ("Axis Bank", ["AXIS BANK"], "UTIB", "Axis Bank A/c"),
    ("Kotak Mahindra Bank", ["KOTAK MAHINDRA", "KOTAK BANK"], "KKBK", "Kotak Bank A/c"),
]

IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
ACCT_RE = re.compile(
    r"(?:a/?c|account)\s*(?:no|number|num|#)?\s*\.?\s*[:\-]?\s*([0-9Xx\*]{6,20})", re.I
)
DATE_TOKEN = r"\d{1,2}[\s/\-.](?:\d{1,2}|[A-Za-z]{3,4})[\s/\-.,]*\d{2,4}"
PERIOD_RE = re.compile(
    rf"(?:from|period|between)\s*:?\s*({DATE_TOKEN})\s*(?:to|till|and|-)\s*:?\s*({DATE_TOKEN})", re.I
)
NAME_RE = re.compile(r"(?:account\s*name|customer\s*name|name)\s*:\s*([A-Za-z][A-Za-z .&]{2,60})", re.I)


def detect_bank(text: str) -> tuple[str, str]:
    """Return (bank display name, default ledger name)."""
    up = text.upper()
    m = IFSC_RE.search(up)
    if m:
        prefix = m.group(1)[:4]
        for name, _, ifsc, ledger in BANKS:
            if prefix == ifsc:
                return name, ledger
    for name, markers, _, ledger in BANKS:
        if any(mk in up for mk in markers):
            return name, ledger
    return "Unknown", "Bank A/c"


def extract_meta(text: str) -> dict:
    meta: dict = {"ifsc": "", "account_number": "", "account_holder": "",
                  "period_from": None, "period_to": None}
    m = IFSC_RE.search(text.upper())
    if m:
        meta["ifsc"] = m.group(1)
    m = ACCT_RE.search(text)
    if m:
        meta["account_number"] = m.group(1)
    m = PERIOD_RE.search(text)
    if m:
        meta["period_from"] = parse_date(m.group(1))
        meta["period_to"] = parse_date(m.group(2))
    m = NAME_RE.search(text)
    if m:
        meta["account_holder"] = m.group(1).strip().split("  ")[0].strip()
    return meta


def find_labelled_amount(text: str, label: str) -> Optional[float]:
    from .utils import parse_amount

    m = re.search(rf"{label}\s*(?:balance)?\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*([\d,]+\.\d{{2}}(?:\s*(?:cr|dr))?)",
                  text, re.I)
    if m:
        return parse_amount(m.group(1))
    return None
