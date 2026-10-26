"""
Generate realistic *synthetic* bank statements (HDFC, SBI, ICICI, Axis, Kotak + tricky variants)
for testing. All names/numbers are fake. Each PDF comes with a JSON "truth" file listing the
transactions that were drawn, so tests can measure exactly what the parser got right.

    python tests/make_samples.py  -> writes samples/*.pdf and samples/*.truth.json
"""
from __future__ import annotations

import json
import random
import textwrap
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"

PEOPLE = ["RAMESH KUMAR", "PRIYA SHARMA", "SRI SAI TRADERS", "MANJUNATH ENTERPRISES", "LAKSHMI STORES",
          "ANAND REDDY", "GREEN LEAF SUPPLIES", "VENKATESH RAO", "K S AGENCIES", "NAVYA TEXTILES"]
VPAS = ["okaxis", "oksbi", "ybl", "paytm", "okicici", "okhdfcbank"]


def fmt_amt(v: float) -> str:
    return f"{v:,.2f}"


def make_txns(seed: int, n: int, start: date, opening: float):
    rnd = random.Random(seed)
    bal = opening
    d = start
    out = []
    for i in range(n):
        d += timedelta(days=rnd.choice([0, 0, 1, 1, 2, 3]))
        kind = rnd.choices(
            ["upi_out", "upi_in", "neft_in", "neft_out", "imps_out", "atm", "charges", "interest", "salary", "emi", "gst", "bill"],
            weights=[22, 18, 10, 8, 6, 5, 4, 2, 3, 2, 2, 4],
        )[0]
        p = rnd.choice(PEOPLE)
        refno = str(rnd.randint(10**11, 10**12 - 1))
        if kind in {"upi_in", "neft_in", "interest", "salary"}:
            amt = round(rnd.uniform(200, 85000), 2) if kind != "interest" else round(rnd.uniform(10, 900), 2)
            debit, credit = 0.0, amt
        else:
            amt = round(rnd.uniform(50, 40000), 2) if kind != "charges" else round(rnd.choice([17.7, 59.0, 118.0, 295.0]), 2)
            debit, credit = amt, 0.0
        bal = round(bal - debit + credit, 2)
        out.append(dict(date=d, kind=kind, party=p, ref=refno, debit=debit, credit=credit, balance=bal,
                        vpa=f"{p.split()[0].lower()}{rnd.randint(1, 99)}@{rnd.choice(VPAS)}"))
    return out


def narration(bank: str, t: dict) -> str:
    p, ref, vpa, k = t["party"], t["ref"], t["vpa"], t["kind"]
    if bank == "HDFC":
        return {
            "upi_out": f"UPI-{p}-{vpa}-HDFC0001234-{ref}-PAYMENT FROM PHONE",
            "upi_in": f"UPI-{p}-{vpa}-SBIN0004567-{ref}-UPI",
            "neft_in": f"NEFT CR-ICIC0000104-{p}-SALES INVOICE {ref[:5]}",
            "neft_out": f"NEFT DR-UTIB0000123-{p}-NETBANK, MUM-N{ref}-VENDOR PAYMENT",
            "imps_out": f"IMPS-{ref}-{p}-KKBK-XXXXXXXX1234-SUPPLIES",
            "atm": f"NWD-512345XXXXXX1234-S1ANBG12-BANGALORE",
            "charges": "SMS CHARGES FOR THE QUARTER INCL GST",
            "interest": "CREDIT INTEREST CAPITALISED",
            "salary": f"SALARY FOR THE MONTH - {p}",
            "emi": f"EMI 4523781 CHQ S45237810021 0624452378",
            "gst": f"GST PAYMENT CPIN 24052900{ref[:6]} CBIC",
            "bill": f"BILLPAY BESCOM ELECTRICITY {ref[:8]}",
        }[k]
    if bank == "SBI":
        return {
            "upi_out": f"TO TRANSFER-UPI/DR/{ref}/{p}/HDFC/{vpa}/Payment",
            "upi_in": f"BY TRANSFER-UPI/CR/{ref}/{p}/ICIC/{vpa}/UPI",
            "neft_in": f"BY TRANSFER-NEFT*ICIC0000104*N{ref}*{p}",
            "neft_out": f"TO TRANSFER-INB NEFT {p} UTR {ref}",
            "imps_out": f"TO TRANSFER-INB IMPS{ref}/{p}/KKBK",
            "atm": "ATM WDL-ATM CASH 4521 MG ROAD BANGALORE",
            "charges": "DEBIT-ATMCARD AMC 4521XXXXXX1234 + GST",
            "interest": "CREDIT- INTEREST",
            "salary": f"BY TRANSFER-NEFT SALARY {p}",
            "emi": f"TO DEBIT THROUGH ECS LOAN EMI {ref[:8]}",
            "gst": f"TO TRANSFER-GST CPIN {ref} OLTAS",
            "bill": f"TO TRANSFER-BILL PAY AIRTEL {ref[:7]}",
        }[k]
    if bank == "ICICI":
        return {
            "upi_out": f"UPI/{ref}/{p}/{vpa}/Payment/ICI{ref[:6]}",
            "upi_in": f"UPI/{ref}/{p}/{vpa}/UPI/YES{ref[:6]}",
            "neft_in": f"NEFT-HDFCN{ref}-{p}-INVOICE PAYMENT",
            "neft_out": f"NEFT-{ref}-{p}-VENDOR",
            "imps_out": f"MMT/IMPS/{ref}/{p}/HDFC0000001",
            "atm": "ATM/CASH WDL/S1CN1234/BANGALORE",
            "charges": "SMS CHGS APR-JUN 24+GST",
            "interest": "INT.PD:01-04-2024 TO 30-06-2024",
            "salary": f"SALARY JUN 24 {p}",
            "emi": f"BIL/ONL/LOAN EMI/{ref[:8]}",
            "gst": f"GST/CBIC/{ref}",
            "bill": f"BIL/BPAY/BESCOM/{ref[:8]}",
        }[k]
    if bank == "AXIS":
        return {
            "upi_out": f"UPI/P2A/{ref}/{p}/HDFC BANK/Payment",
            "upi_in": f"UPI/P2A/{ref}/{p}/State Bank/UPI",
            "neft_in": f"NEFT/ICIC{ref[:7]}/{p}/ICICI BANK",
            "neft_out": f"NEFT/AXOIC{ref[:7]}/{p}/HDFC BANK",
            "imps_out": f"IMPS/P2A/{ref}/{p}/KOTAK",
            "atm": "ATM-CASH/AXIS/BANGALORE/1234",
            "charges": "Consolidated Charges for A/c incl GST",
            "interest": "Int.Pd:1234567:01-04-2024 to 30-06-2024",
            "salary": f"SALARY/{p}/JUNE",
            "emi": f"ACH-DR/LOAN EMI/{ref[:9]}",
            "gst": f"GST PAYMENT/{ref}",
            "bill": f"BBPS/JIO/RECHARGE/{ref[:8]}",
        }[k]
    # KOTAK
    return {
        "upi_out": f"UPI/{p}/{ref}/Payment to {vpa}",
        "upi_in": f"UPI/{p}/{ref}/Received from {vpa}",
        "neft_in": f"NEFT ICIC{ref[:7]} {p}",
        "neft_out": f"NEFT TO {p} {ref[:9]}",
        "imps_out": f"IMPS-{ref}-{p}-HDFC",
        "atm": "ATW-512345XXXXXX1234-CASH WITHDRAWAL",
        "charges": "Chrg: Debit Card Annual Fee incl GST",
        "interest": "Int.Pd:01-04-24 to 30-06-24",
        "salary": f"SALARY CREDIT {p}",
        "emi": f"NACH-DR LOAN EMI {ref[:8]}",
        "gst": f"GST/CBIC/{ref[:10]}",
        "bill": f"BILL PAID ACT FIBERNET {ref[:6]}",
    }[k]


# ---------------------------------------------------------------------------------------------
# Layout definitions: list of columns (header lines, x, width, align, field)
# ---------------------------------------------------------------------------------------------

def dfmt(style: str, d: date) -> str:
    return {
        "dd/mm/yy": d.strftime("%d/%m/%y"),
        "dd/mm/yyyy": d.strftime("%d/%m/%Y"),
        "d Mon yyyy": f"{d.day} {d.strftime('%b %Y')}",
        "dd-mm-yyyy": d.strftime("%d-%m-%Y"),
        "dd-Mon-yyyy": d.strftime("%d-%b-%Y"),
    }[style]


LAYOUTS = {
    "HDFC": dict(
        title="HDFC BANK Ltd.", ifsc="HDFC0001234", date_style="dd/mm/yy", wrap=34, landscape=False,
        cols=[(["Date"], 30, 45, "l", "date"), (["Narration"], 78, 190, "l", "narr"),
              (["Chq./Ref.No."], 272, 75, "l", "ref"), (["Value Dt"], 350, 42, "l", "vdate"),
              (["Withdrawal Amt."], 395, 62, "r", "debit"), (["Deposit Amt."], 460, 60, "r", "credit"),
              (["Closing Balance"], 523, 62, "r", "bal")],
    ),
    "SBI": dict(
        title="State Bank of India", ifsc="SBIN0004567", date_style="d Mon yyyy", wrap=36, landscape=False,
        cols=[(["Txn Date"], 30, 50, "l", "date"), (["Value", "Date"], 82, 50, "l", "vdate"),
              (["Description"], 135, 180, "l", "narr"), (["Ref No./", "Cheque No."], 318, 70, "l", "ref"),
              (["Debit"], 392, 58, "r", "debit"), (["Credit"], 455, 58, "r", "credit"),
              (["Balance"], 518, 66, "r", "bal")],
    ),
    "ICICI": dict(
        title="ICICI Bank Limited", ifsc="ICIC0000104", date_style="dd/mm/yyyy", wrap=40, landscape=True,
        centered=True,
        cols=[(["S No."], 30, 25, "l", "sno"), (["Value", "Date"], 60, 55, "l", "vdate"),
              (["Transaction", "Date"], 120, 55, "l", "date"), (["Cheque", "Number"], 180, 60, "l", "ref"),
              (["Transaction Remarks"], 245, 230, "l", "narr"),
              (["Withdrawal", "Amount (INR )"], 480, 85, "r", "debit"),
              (["Deposit", "Amount (INR )"], 570, 85, "r", "credit"),
              (["Balance (INR )"], 660, 90, "r", "bal")],
    ),
    "AXIS": dict(
        title="AXIS BANK", ifsc="UTIB0000123", date_style="dd-mm-yyyy", wrap=38, landscape=False,
        cols=[(["Tran Date"], 30, 50, "l", "date"), (["Chq No"], 84, 40, "l", "ref"),
              (["Particulars"], 128, 200, "l", "narr"), (["Debit"], 332, 60, "r", "debit"),
              (["Credit"], 396, 60, "r", "credit"), (["Balance"], 460, 70, "r", "bal"),
              (["Init.", "Br"], 540, 30, "l", "branch")],
    ),
    "KOTAK": dict(
        title="Kotak Mahindra Bank", ifsc="KKBK0000958", date_style="dd-mm-yyyy", wrap=36, landscape=False,
        bal_suffix=True,
        cols=[(["Date"], 30, 50, "l", "date"), (["Narration"], 84, 190, "l", "narr"),
              (["Chq/Ref No"], 278, 80, "l", "ref"), (["Withdrawal (Dr)"], 362, 68, "r", "debit"),
              (["Deposit (Cr)"], 434, 64, "r", "credit"), (["Balance"], 502, 80, "r", "bal")],
    ),
    # Tricky variant: single Amount column + Dr/Cr indicator, newest transactions first.
    "KOTAK_AMOUNT_DESC": dict(
        bank="KOTAK", title="Kotak Mahindra Bank", ifsc="KKBK0000958", date_style="dd-Mon-yyyy", wrap=40,
        landscape=False, newest_first=True,
        cols=[(["Date"], 30, 60, "l", "date"), (["Description"], 95, 230, "l", "narr"),
              (["Amount"], 330, 75, "r", "amount"), (["Dr / Cr"], 410, 30, "l", "drcr"),
              (["Balance"], 450, 80, "r", "bal")],
    ),
}


def build(name: str, seed: int, n: int = 60, password: str | None = None) -> Path:
    lay = LAYOUTS[name]
    bank = lay.get("bank", name)
    opening = round(random.Random(seed).uniform(20000, 250000), 2)
    txns = make_txns(seed, n, date(2024, 4, 1), opening)
    for t in txns:
        t["narration"] = narration(bank, t)
    rows = list(reversed(txns)) if lay.get("newest_first") else txns

    OUT.mkdir(exist_ok=True)
    fname = name.lower() + ("_locked" if password else "")
    path = OUT / f"{fname}.pdf"
    size = landscape(A4) if lay["landscape"] else A4
    W, H = size
    c = canvas.Canvas(str(path), pagesize=size)
    if password:
        from reportlab.lib import pdfencrypt
        c = canvas.Canvas(str(path), pagesize=size,
                          encrypt=pdfencrypt.StandardEncryption(password, canPrint=1))
    fs = 7.2
    lh = 9.0

    def header_block(page_no: int, pages: int):
        y = H - 40
        c.setFont("Helvetica-Bold", 13)
        c.drawString(30, y, lay["title"])
        c.setFont("Helvetica", 8)
        if page_no == 1:
            c.drawString(30, y - 16, "Account Name : DEMO TRADING COMPANY")
            c.drawString(30, y - 27, "Account No : 50100123456789")
            c.drawString(30, y - 38, f"IFSC : {lay['ifsc']}    Branch : KORAMANGALA, BANGALORE")
            c.drawString(30, y - 49, f"Statement From : {dfmt('dd/mm/yyyy', date(2024, 4, 1))} To : {dfmt('dd/mm/yyyy', txns[-1]['date'])}")
            y -= 72
        else:
            c.drawString(W - 120, y, f"Page No .: {page_no}")
            y -= 26
        # table header
        c.setFont("Helvetica-Bold", fs)
        max_lines = max(len(h) for h, *_ in lay["cols"])
        for hdr, x, w, al, _f in lay["cols"]:
            for k, txt in enumerate(hdr):
                yy = y - k * lh
                if al == "r":
                    c.drawRightString(x + w, yy, txt)
                else:
                    c.drawString(x, yy, txt)
        y -= max_lines * lh + 6
        c.line(28, y + 6, W - 28, y + 6)
        c.setFont("Helvetica", fs)
        return y

    # paginate
    per_page_lines = 62 if not lay["landscape"] else 40
    pages: list[list[dict]] = [[]]
    used = 0
    for t in rows:
        nl = len(textwrap.wrap(t["narration"], lay["wrap"]))
        if used + nl > per_page_lines and pages[-1]:
            pages.append([])
            used = 0
        pages[-1].append(t)
        used += nl + 0.4

    sno = 0
    for pi, prow in enumerate(pages, 1):
        y = header_block(pi, len(pages))
        if pi == 1 and not lay.get("newest_first"):
            c.drawString(lay["cols"][0][1], y, dfmt(lay["date_style"], date(2024, 4, 1)) if bank == "SBI" else "")
            narr_x = next(x for _h, x, _w, _a, f in lay["cols"] if f == "narr")
            c.drawString(narr_x, y, "Opening Balance" if bank != "SBI" else "Balance as on 1 Apr 2024")
            bx = next((x + w for _h, x, w, _a, f in lay["cols"] if f == "bal"))
            c.drawRightString(bx, y, fmt_amt(opening))
            y -= lh * 1.4
        for t in prow:
            sno += 1
            lines = textwrap.wrap(t["narration"], lay["wrap"])
            main_y = y - (len(lines) - 1) / 2 * lh if lay.get("centered") else y
            # snap to a line slot for centered layouts
            if lay.get("centered") and len(lines) > 1:
                main_y = y - ((len(lines) - 1) // 2) * lh
            for hdr, x, w, al, f in lay["cols"]:
                if f == "narr":
                    for k, ln in enumerate(lines):
                        c.drawString(x, y - k * lh, ln)
                    continue
                val = {
                    "date": dfmt(lay["date_style"], t["date"]),
                    "vdate": dfmt(lay["date_style"], t["date"]),
                    "ref": (t["ref"][:12] if t["kind"] in {"neft_out", "neft_in", "imps_out", "emi"} else ("00" + t["ref"][:9])),
                    "debit": fmt_amt(t["debit"]) if t["debit"] else "",
                    "credit": fmt_amt(t["credit"]) if t["credit"] else "",
                    "bal": fmt_amt(t["balance"]) + (" Cr" if lay.get("bal_suffix") else ""),
                    "amount": fmt_amt(t["debit"] or t["credit"]),
                    "drcr": "DR" if t["debit"] else "CR",
                    "sno": str(sno),
                    "branch": "123",
                }[f]
                if bank == "AXIS" and f == "ref":
                    val = ""
                if al == "r":
                    c.drawRightString(x + w, main_y, val)
                else:
                    c.drawString(x, main_y, val)
            y -= len(lines) * lh + 3
        c.setFont("Helvetica", 7)
        c.drawString(30, 30, f"Page {pi} of {len(pages)}")
        if pi == len(pages):
            c.setFont("Helvetica-Bold", 8)
            c.drawString(30, y - 20, "STATEMENT SUMMARY :-")
            c.setFont("Helvetica", 8)
            c.drawString(30, y - 32, f"Opening Balance : {fmt_amt(opening)}   Closing Balance : {fmt_amt(txns[-1]['balance'])}")
            c.drawString(30, y - 44, "This is a computer generated statement and does not require signature.")
        c.showPage()
        c.setFont("Helvetica", fs)
    c.save()

    truth = dict(bank=bank, opening=opening, closing=txns[-1]["balance"], transactions=[
        dict(date=t["date"].isoformat(), debit=t["debit"], credit=t["credit"], balance=t["balance"],
             narration=t["narration"], party=t["party"], kind=t["kind"]) for t in txns])
    (OUT / f"{fname}.truth.json").write_text(json.dumps(truth, indent=1))
    return path


def build_all() -> list[Path]:
    paths = []
    for i, name in enumerate(LAYOUTS):
        paths.append(build(name, seed=100 + i))
    paths.append(build("HDFC", seed=999, n=25, password="DEMO1234"))
    return paths


if __name__ == "__main__":
    for p in build_all():
        print("wrote", p)
