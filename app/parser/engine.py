"""
Layout-aware bank statement parser.

How it works
------------
1. Read every word on every page with its x/y position (pdfplumber).
2. Find the table header row (a line containing "Date" and "Balance"), including headers that
   wrap onto two lines, and turn it into columns with a role: date, narration, ref, debit,
   credit, amount, dr/cr, balance...
3. Walk the lines under the header. A line whose date-column holds a valid date starts a new
   transaction; other lines are wrapped narration that belongs to the nearest transaction.
4. Reconcile: opening balance - debit + credit must equal each row's balance. This catches
   parsing mistakes, fixes swapped debit/credit, and resolves single "Amount" columns.

No bank-specific templates are needed for the common layouts; profiles in detect.py only
name the bank and its default ledger.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber

from .detect import detect_bank, extract_meta, find_labelled_amount
from .models import Statement, Transaction
from .utils import looks_like_amount, parse_amount, parse_date


class PasswordRequired(Exception):
    pass


class WrongPassword(Exception):
    pass


class NoTextLayer(Exception):
    """The PDF is a scan/image - needs OCR."""


class TableNotFound(Exception):
    pass


NUMERIC_ROLES = {"debit", "credit", "amount", "balance"}
TEXT_ROLES = {"narration", "ref"}

FOOTER_STOP = re.compile(
    r"statement summary|closing balance|grand total|page total|\btotal\b|\*+\s*end|end of statement|"
    r"computer generated|disclaimer|abbreviations|registered office|this is a system", re.I)
FOOTER_SKIP = re.compile(r"^page\s*(no\.?)?\s*:?\s*\d+|page \d+ of \d+|continued|contd", re.I)
OPENING_RE = re.compile(r"opening balance|balance b/?f|brought forward|balance as on|b/f", re.I)


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    words: list[Word]
    top: float
    bottom: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Column:
    role: str
    label: str
    x0: float
    x1: float


@dataclass
class _Row:
    txn: Transaction
    top: float
    bottom: float
    page: int
    amount_dir_unknown: bool = False
    narr: list[tuple[str, float]] = field(default_factory=list)  # (text, right edge x1)


# ---------------------------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------------------------

def _words(page) -> list[Word]:
    raw = page.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False)
    return [Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"]) for w in raw]


def _lines(words: list[Word], tol: float = 2.5) -> list[Line]:
    words = sorted(words, key=lambda w: (round(w.top, 1), w.x0))
    lines: list[Line] = []
    for w in words:
        if lines and abs(w.top - lines[-1].top) <= tol:
            lines[-1].words.append(w)
            lines[-1].bottom = max(lines[-1].bottom, w.bottom)
        else:
            lines.append(Line([w], w.top, w.bottom))
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
        ln.words = _merge_suffixes(ln.words)
    return lines


def _merge_suffixes(words: list[Word]) -> list[Word]:
    """Glue 'Cr'/'Dr' that sit next to an amount onto that amount: '1,200.00' 'Cr' -> '1,200.00 Cr'."""
    out: list[Word] = []
    for w in words:
        if (out and w.text.lower().strip("()") in {"cr", "dr"} and looks_like_amount(out[-1].text)
                and w.x0 - out[-1].x1 < 8):
            p = out[-1]
            out[-1] = Word(f"{p.text} {w.text}", p.x0, w.x1, p.top, max(p.bottom, w.bottom))
        else:
            out.append(w)
    return out


# ---------------------------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------------------------

def _classify(label: str) -> str:
    s = label.lower()
    s_compact = re.sub(r"[^a-z/()]", " ", s)
    if "balance" in s:
        return "balance"
    if re.search(r"withdraw|debit|paid out|\bdr\b|\(dr\)", s) and not re.search(r"deposit|credit|\bcr\b", s):
        return "debit"
    if re.search(r"deposit|credit|paid in|\bcr\b|\(cr\)", s) and not re.search(r"withdraw|debit|\bdr\b", s):
        return "credit"
    if re.search(r"dr\s*/\s*cr|cr\s*/\s*dr|type", s):
        return "drcr"
    if "value" in s:
        return "value_date"
    if re.search(r"chq|cheque|ref|instrument|utr", s):
        return "ref"
    if re.search(r"\bdate\b|\bdt\b|\bdt\.|txn date|tran date", s_compact + " "):
        return "date"
    if re.search(r"narration|description|particular|remark|details|transaction", s):
        return "narration"
    if "amount" in s or "amt" in s:
        return "amount"
    if re.search(r"s\.?\s*no|sl\.?|sr\.?|#", s):
        return "serial"
    return "other"


def _is_header_line(ln: Line) -> bool:
    t = ln.text.lower()
    return "balance" in t and bool(re.search(r"\bdate\b|\bdt\b|\bdt\.|date", t)) and len(ln.words) >= 3


def _line_has_data(ln: Line) -> bool:
    return any(looks_like_amount(w.text) or parse_date(w.text) for w in ln.words)


def _overlaps(a: Word, b: Word) -> bool:
    return min(a.x1, b.x1) - max(a.x0, b.x0) > 0


def _build_columns(header_lines: list[Line]) -> list[Column]:
    words = [w for ln in header_lines for w in ln.words]
    parent = list(range(len(words)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i, a in enumerate(words):
        for j in range(i + 1, len(words)):
            b = words[j]
            same_line = abs(a.top - b.top) < 2.5
            if same_line:
                left, right = (a, b) if a.x0 < b.x0 else (b, a)
                if 0 <= right.x0 - left.x1 < 4.0:
                    union(i, j)
            elif _overlaps(a, b):
                union(i, j)

    groups: dict[int, list[Word]] = {}
    for i, w in enumerate(words):
        groups.setdefault(find(i), []).append(w)

    cols: list[Column] = []
    for ws in groups.values():
        ws.sort(key=lambda w: (round(w.top), w.x0))
        label = " ".join(w.text for w in ws)
        cols.append(Column(_classify(label), label, min(w.x0 for w in ws), max(w.x1 for w in ws)))
    cols.sort(key=lambda c: c.x0)

    # Resolve duplicated roles: prefer "transaction date" over "value date", keep first otherwise.
    seen: set[str] = set()
    for c in cols:
        if c.role in seen and c.role not in {"other", "serial"}:
            c.role = "other"
        seen.add(c.role)
    return cols


def _find_header(lines: list[Line]) -> Optional[tuple[int, int, list[Column]]]:
    """Return (first header line idx, last header line idx, columns) or None."""
    for i, ln in enumerate(lines):
        if not _is_header_line(ln):
            # Headers wrapped over two lines ("Transaction" / "Date") - test the pair together.
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if not (nxt and nxt.top - ln.top < 13 and not _line_has_data(nxt) and not _line_has_data(ln)
                    and _is_header_line(Line(ln.words + nxt.words, ln.top, nxt.bottom))):
                continue
        group = [ln]
        lo = hi = i
        # Wrapped header words directly above / below, stacked over the main header words.
        for j in (i - 1, i + 1, i + 2):
            if j < 0 or j >= len(lines) or j == i:
                continue
            cand = lines[j]
            ref = lines[j + 1] if j < i else lines[j - 1]
            if abs(cand.top - ref.top) > 13 or _line_has_data(cand):
                if j > i:
                    break
                continue
            if ":" not in cand.text and all(any(_overlaps(w, h) for h in ln.words) for w in cand.words):
                group.append(cand)
                lo, hi = min(lo, j), max(hi, j)
            elif j > i:
                break
        cols = _build_columns(group)
        roles = {c.role for c in cols}
        if "date" not in roles and "value_date" in roles:
            for c in cols:
                if c.role == "value_date":
                    c.role = "date"
                    break
            roles = {c.role for c in cols}
        if "date" in roles and "balance" in roles and (
            {"debit", "credit"} <= roles or "amount" in roles or "debit" in roles or "credit" in roles
        ):
            return lo, hi, cols
    return None


# ---------------------------------------------------------------------------------------------
# Assigning body words to columns
# ---------------------------------------------------------------------------------------------

def _assign(ln: Line, cols: list[Column]) -> dict[str, list[str]]:
    cells: dict[str, list[str]] = {}
    numeric = [c for c in cols if c.role in NUMERIC_ROLES]
    for w in ln.words:
        target: Optional[Column] = None
        if looks_like_amount(w.text) and numeric:
            best = min(numeric, key=lambda c: min(abs(w.x1 - c.x1), abs(w.cx - (c.x0 + c.x1) / 2)))
            dist = min(abs(w.x1 - best.x1), abs(w.cx - (best.x0 + best.x1) / 2))
            if dist < 45:
                target = best
        if target is None:
            # Left-aligned text: the right-most column that starts at or before this word.
            starts = [c for c in cols if c.x0 <= w.x0 + 3]
            target = starts[-1] if starts else cols[0]
            if target.role in NUMERIC_ROLES and not looks_like_amount(w.text):
                # A stray text word under a numeric column belongs to the nearest text column.
                txt = [c for c in cols if c.role in TEXT_ROLES]
                if txt:
                    target = min(txt, key=lambda c: abs(c.x0 - w.x0))
        cells.setdefault(target.role, []).append(w.text)
    return cells


def _cell(cells: dict[str, list[str]], role: str) -> str:
    return " ".join(cells.get(role, [])).strip()


def _narr_seg(ln: Line, cols: list[Column]) -> tuple[str, float]:
    """Narration text on a line plus the x1 of its last word (to detect a hard-wrapped line)."""
    ncol = next((c for c in cols if c.role == "narration"), None)
    if ncol is None:
        return "", 0.0
    cells_words = [w for w in ln.words if _assign(Line([w], ln.top, ln.bottom), cols).get("narration")]
    if not cells_words:
        return "", 0.0
    return " ".join(w.text for w in cells_words), max(w.x1 for w in cells_words)


def join_narration(segs: list[tuple[str, float]], limit: float) -> str:
    out = ""
    prev_x1 = 0.0
    for text, x1 in segs:
        if not text:
            continue
        if out and prev_x1 >= limit - 4.5 and out[-1].isalnum() and text[0].isalnum():
            out += text  # the bank hard-wrapped mid-word at the column edge
        elif out:
            out += " " + text
        else:
            out = text
        prev_x1 = x1
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------------------------

def parse_pdf(data: bytes, password: Optional[str] = None) -> Statement:
    try:
        pdf = pdfplumber.open(io.BytesIO(data), password=password or "")
        _ = pdf.pages  # force decryption
    except Exception as e:  # pdfminer raises several types for encryption problems
        desc = f"{type(e).__name__} {e!r}".lower()
        if "password" in desc or "encrypt" in desc:
            if password:
                raise WrongPassword("The password is incorrect.") from e
            raise PasswordRequired("This PDF is password protected.") from e
        raise

    with pdf:
        pages_lines: list[list[Line]] = []
        texts: list[str] = []
        for page in pdf.pages:
            ws = _words(page)
            pages_lines.append(_lines(ws))
            texts.append(page.extract_text() or "")
        full_text = "\n".join(texts)
        n_pages = len(pdf.pages)

    if len(full_text.strip()) < 40:
        raise NoTextLayer("This looks like a scanned statement (no text layer).")

    st = Statement(pages=n_pages)
    st.bank, _ = detect_bank(full_text)
    meta = extract_meta(full_text)
    st.ifsc = meta["ifsc"]
    st.account_number = meta["account_number"]
    st.account_holder = meta["account_holder"]
    st.period_from = meta["period_from"]
    st.period_to = meta["period_to"]

    rows = _parse_rows(pages_lines, st)
    if not rows:
        raise TableNotFound("Couldn't find a transactions table in this PDF.")

    limit = max((x1 for r in rows for _t, x1 in r.narr), default=0.0)
    for r in rows:
        r.txn.narration = join_narration(r.narr, limit)
        st.transactions.append(r.txn)
    unknown_dir = {id(r.txn) for r in rows if r.amount_dir_unknown}

    if st.opening_balance is None:
        st.opening_balance = find_labelled_amount(full_text, "opening")
    _order_and_reconcile(st, unknown_dir)
    closing = find_labelled_amount(full_text, "closing")
    if closing is not None and st.closing_balance is not None and abs(closing - st.closing_balance) > 0.01:
        st.warnings.append(
            f"Closing balance printed on statement ({closing:,.2f}) differs from the last row ({st.closing_balance:,.2f})."
        )
    return st


def _parse_rows(pages_lines: list[list[Line]], st: Statement) -> list[_Row]:
    rows: list[_Row] = []
    cols: Optional[list[Column]] = None
    line_h = 10.0

    for pno, lines in enumerate(pages_lines):
        start = 0
        hdr = _find_header(lines)
        if hdr:
            _, hi, cols = hdr
            start = hi + 1
        if cols is None:
            continue

        pending: list[tuple[Line, dict]] = []
        stopped = False
        page_rows_before = len(rows)

        for ln in lines[start:]:
            text = ln.text
            if stopped:
                # A repeated header later on the same page restarts parsing.
                if _is_header_line(ln):
                    stopped = False
                continue
            if _is_header_line(ln):
                continue
            if FOOTER_SKIP.search(text):
                continue
            cells = _assign(ln, cols)
            d = parse_date(_cell(cells, "date"))
            if d is None and cells.get("date"):
                # Date words sometimes include a time or serial; try the first 1-3 tokens.
                toks = cells["date"]
                for k in (3, 2, 1):
                    d = parse_date(" ".join(toks[:k]))
                    if d:
                        break

            if d is None:
                if OPENING_RE.search(text) and not rows:
                    amt = [parse_amount(x) for x in (cells.get("balance") or [])]
                    amt = [a for a in amt if a is not None]
                    if amt:
                        st.opening_balance = amt[-1]
                    continue
                if FOOTER_STOP.search(text) and len(rows) > page_rows_before:
                    stopped = True
                    _flush(pending, rows, pno, line_h, to_prev_only=True, cols=cols)
                    pending = []
                    continue
                pending.append((ln, cells))
                continue

            # A row with a date but no amounts: either an opening-balance row or a narration line.
            narr_text = _cell(cells, "narration")
            if OPENING_RE.search(narr_text or text) and not any(cells.get(r) for r in ("debit", "credit", "amount")):
                bal = parse_amount(_cell(cells, "balance"))
                if bal is not None and not rows:
                    st.opening_balance = bal
                continue

            row = _make_row(d, cells, ln, pno, cols)
            if row is None:
                pending.append((ln, cells))
                continue
            line_h = max(6.0, min(14.0, ln.bottom - ln.top + 2))
            # Distribute pending wrapped lines between previous and this row.
            prev = rows[-1] if rows and rows[-1].page == pno else None
            for pl, pc in pending:
                gap_prev = (pl.top - prev.bottom) if prev else 1e9
                gap_next = ln.top - pl.bottom
                if not _is_continuation(pc):
                    continue
                if min(gap_prev, gap_next) > 3.2 * line_h:
                    continue
                if prev is not None and gap_prev <= gap_next:
                    _absorb(prev, pc, pl, cols)
                else:
                    row.narr.insert(0, _narr_seg(pl, cols))
                    _merge_ref(row.txn, _cell(pc, "ref"))
            pending = []
            rows.append(row)

        _flush(pending, rows, pno, line_h, to_prev_only=True, cols=cols)
    return rows


def _is_continuation(cells: dict) -> bool:
    roles = {r for r, v in cells.items() if v}
    return bool(roles & {"narration", "ref"}) and roles <= {"narration", "ref", "other", "value_date", "serial"}


def _absorb(row: _Row, cells: dict, ln: Line, cols: list[Column]) -> None:
    row.narr.append(_narr_seg(ln, cols))
    _merge_ref(row.txn, _cell(cells, "ref"))
    row.bottom = max(row.bottom, ln.bottom)


def _merge_ref(t: Transaction, ref: str) -> None:
    if ref:
        t.ref = (t.ref + ref) if t.ref and not t.ref.endswith(" ") and ref[0].isdigit() and t.ref[-1].isdigit() else (f"{t.ref} {ref}".strip())


def _flush(pending, rows: list[_Row], pno: int, line_h: float, to_prev_only: bool, cols=None) -> None:
    if not pending or not rows:
        return
    prev = rows[-1]
    if prev.page != pno:
        return
    for pl, pc in pending:
        if _is_continuation(pc) and pl.top - prev.bottom <= 3.2 * line_h:
            _absorb(prev, pc, pl, cols)


def _make_row(d, cells: dict, ln: Line, pno: int, cols: list[Column]) -> Optional[_Row]:
    debit = parse_amount(_cell(cells, "debit")) if cells.get("debit") else None
    credit = parse_amount(_cell(cells, "credit")) if cells.get("credit") else None
    balance = parse_amount(_cell(cells, "balance")) if cells.get("balance") else None
    unknown = False
    if cells.get("amount"):
        amt_txt = _cell(cells, "amount")
        amt = parse_amount(amt_txt)
        ind = (_cell(cells, "drcr") + " " + amt_txt).lower()
        if amt is not None:
            if re.search(r"\bdr\b|debit|\bd\b", ind):
                debit = abs(amt)
            elif re.search(r"\bcr\b|credit|\bc\b", ind):
                credit = abs(amt)
            elif amt < 0:
                debit = abs(amt)
            else:
                debit = amt
                unknown = True
    if debit is None and credit is None:
        return None
    t = Transaction(
        date=d,
        ref=_cell(cells, "ref"),
        value_date=parse_date(_cell(cells, "value_date")),
        debit=abs(debit or 0.0),
        credit=abs(credit or 0.0),
        balance=balance,
    )
    row = _Row(t, ln.top, ln.bottom, pno, amount_dir_unknown=unknown)
    row.narr.append(_narr_seg(ln, cols))
    return row


# ---------------------------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------------------------

def _order_and_reconcile(st: Statement, unknown_dir: set[int]) -> None:
    txns = st.transactions
    if len(txns) >= 2 and txns[0].date > txns[-1].date:
        txns.reverse()
        st.warnings.append("Statement was in newest-first order; rows were re-ordered oldest-first.")

    prev = st.opening_balance
    if prev is None and txns and txns[0].balance is not None:
        t = txns[0]
        if id(t) in unknown_dir:
            prev = None
        else:
            prev = round(t.balance + t.debit - t.credit, 2)
            st.opening_balance = prev

    bad = 0
    for t in txns:
        if t.balance is None:
            t.reconciled = None
            if prev is not None:
                prev = round(prev - t.debit + t.credit, 2)
            continue
        if prev is None:
            prev = t.balance
            t.reconciled = None
            continue
        amount = t.debit or t.credit
        if id(t) in unknown_dir:
            if abs(prev + amount - t.balance) < 0.011:
                t.debit, t.credit = 0.0, amount
            else:
                t.debit, t.credit = amount, 0.0
        if abs(prev - t.debit + t.credit - t.balance) < 0.011:
            t.reconciled = True
        elif abs(prev + t.debit - t.credit - t.balance) < 0.011:
            t.debit, t.credit = t.credit, t.debit
            t.reconciled = True
            t.note = "Debit/credit side corrected using running balance"
        else:
            t.reconciled = False
            t.note = f"Balance mismatch: expected {prev - t.debit + t.credit:,.2f}"
            bad += 1
        prev = t.balance

    if txns:
        st.closing_balance = txns[-1].balance if txns[-1].balance is not None else prev
    if bad:
        st.warnings.append(f"{bad} row(s) don't match the running balance - please review them (highlighted).")
