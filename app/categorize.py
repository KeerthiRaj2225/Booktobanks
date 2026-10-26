"""Suggest a counter-party name, Tally ledger and voucher type for each bank transaction."""
from __future__ import annotations

import re

from .parser.models import Statement, Transaction

# keyword regex -> (ledger name, Tally parent group, voucher type override or None)
RULES: list[tuple[re.Pattern, str, str, str | None]] = [
    (re.compile(r"\batm\b|cash wdl|cash withdrawal|\batw\b|\bnwd\b|self\s*chq|by cash|cash dep|cdm", re.I),
     "Cash", "Cash-in-Hand", "Contra"),
    (re.compile(r"charges?|chgs|\bchg\b|sms alert|annual fee|amc|min bal|non[- ]?maint|gst on|service tax|penal", re.I),
     "Bank Charges", "Indirect Expenses", None),
    (re.compile(r"int\.?\s*pd|interest (paid|credit|cr)|int\.?\s*cr|sb int|credit[-\s]*interest", re.I),
     "Bank Interest Received", "Indirect Incomes", None),
    (re.compile(r"\bgst\b|gstn|cbdt|tds|tin\s*\d|advance tax|income tax|\bcbic\b|oltas", re.I),
     "Taxes & Duties", "Duties & Taxes", None),
    (re.compile(r"\bemi\b|loan|ln\s*rec", re.I), "Loan EMI", "Loans (Liability)", None),
    (re.compile(r"salary|sal\s*for|payroll", re.I), "Salary", "Indirect Expenses", None),
    (re.compile(r"\brent\b", re.I), "Rent", "Indirect Expenses", None),
    (re.compile(r"electricity|bescom|tneb|msedcl|bses|power bill", re.I), "Electricity Charges", "Indirect Expenses", None),
    (re.compile(r"airtel|jio|vodafone|\bvi\b|bsnl|act fibernet|broadband|recharge", re.I), "Telephone & Internet", "Indirect Expenses", None),
    (re.compile(r"swiggy|zomato", re.I), "Staff Welfare", "Indirect Expenses", None),
    (re.compile(r"amazon|flipkart", re.I), "Purchases - Online", "Purchase Accounts", None),
    (re.compile(r"fuel|petrol|hpcl|bpcl|iocl|indian oil", re.I), "Fuel Expenses", "Indirect Expenses", None),
    (re.compile(r"insurance|lic\b|premium", re.I), "Insurance", "Indirect Expenses", None),
    (re.compile(r"mutual fund|\bmf\b|sip|zerodha|groww|nse|bse", re.I), "Investments", "Investments", None),
]

SUSPENSE = ("Suspense A/c", "Suspense A/c")
NO_PARTY = {"Cash", "Bank Charges", "Bank Interest Received", "Taxes & Duties", "Loan EMI"}

_MODES = {
    "upi", "neft", "imps", "rtgs", "dr", "cr", "p2a", "p2m", "p2p", "mb", "ib", "inb", "trf", "transfer",
    "to", "from", "by", "mmt", "ach", "nach", "ecs", "chq", "clg", "inft", "fund", "funds", "trfr",
    "payment", "pay", "paid", "sent", "using", "upi-", "neft-", "imps-", "bil", "onl", "ref", "txn", "na",
    "collect", "request", "utr", "cpin", "received", "credit", "debit", "inb", "via", "mobile", "banking", "netbanking", "net", "to:", "from:", "ybl", "okaxis",
    "salary", "sal", "for", "the", "month", "interest", "bill", "billpay",
}
_BANK_CODES = re.compile(r"^(sbin|hdfc|icic|utib|kkbk|yesb|punb|barb|cnrb|ubin|idib|ioba|idfb|indb|fdrl|ratn|aubl|paytm|pytm)\w*$", re.I)


def extract_party(narration: str) -> str:
    n = narration.strip()
    if not n:
        return ""
    tokens = re.split(r"[/\-:|*]+|\s{2,}", n)
    for raw in tokens:
        tok = raw.strip().strip(".")
        if len(tok) < 3:
            continue
        low = tok.lower()
        if low in _MODES or "@" in tok or _BANK_CODES.match(tok):
            continue
        letters = sum(c.isalpha() for c in tok)
        digits = sum(c.isdigit() for c in tok)
        if letters < 3 or digits > letters:
            continue
        if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", tok):  # IFSC
            continue
        words = [w for w in tok.split()
                 if w.lower() not in _MODES and sum(ch.isdigit() for ch in w) < 3 and not _BANK_CODES.match(w)]
        if not words:
            continue
        name = " ".join(words)
        return name.title()[:60]
    return ""


def categorize_txn(t: Transaction) -> None:
    text = f"{t.narration} {t.ref}"
    t.party = t.party or extract_party(t.narration)
    for rx, ledger, _group, vtype in RULES:
        if rx.search(text):
            if ledger in NO_PARTY:
                t.party = ""
            t.ledger = t.ledger or ledger
            t.voucher_type = t.voucher_type or (vtype or ("Payment" if t.debit else "Receipt"))
            return
    t.ledger = t.ledger or SUSPENSE[0]
    t.voucher_type = t.voucher_type or ("Payment" if t.debit else "Receipt")


def categorize(st: Statement) -> Statement:
    for t in st.transactions:
        categorize_txn(t)
    return st


def ledger_group(ledger: str, is_receipt: bool = False) -> str:
    for _rx, name, group, _v in RULES:
        if name == ledger:
            return group
    if ledger == SUSPENSE[0]:
        return SUSPENSE[1]
    # Custom party ledgers typed by the user: customers who pay us vs suppliers we pay.
    return "Sundry Debtors" if is_receipt else "Sundry Creditors"
