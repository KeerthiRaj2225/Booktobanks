"""
Tally Prime / Tally ERP 9 XML import.

Two files:
  * masters  - creates the ledgers used (import once; existing ledgers are left alone by Tally)
  * vouchers - Payment / Receipt / Contra vouchers against the bank ledger

Import in Tally Prime: Gateway > Import > Masters (ledgers file) then Import > Transactions
(vouchers file). Tally sign convention: debit = negative amount with ISDEEMEDPOSITIVE=Yes,
credit = positive amount with ISDEEMEDPOSITIVE=No.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from ..categorize import ledger_group
from ..parser.models import Statement, Transaction


def _env(body: str, report: str, company: str) -> str:
    company_xml = (
        f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES>"
        if company else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<ENVELOPE>\n"
        " <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>\n"
        " <BODY>\n  <IMPORTDATA>\n"
        f"   <REQUESTDESC><REPORTNAME>{report}</REPORTNAME>{company_xml}</REQUESTDESC>\n"
        "   <REQUESTDATA>\n"
        f"{body}"
        "   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>\n"
    )


def _entry(ledger: str, amount: float, is_debit: bool) -> str:
    amt = -abs(amount) if is_debit else abs(amount)
    return (
        "      <ALLLEDGERENTRIES.LIST>\n"
        f"       <LEDGERNAME>{escape(ledger)}</LEDGERNAME>\n"
        f"       <ISDEEMEDPOSITIVE>{'Yes' if is_debit else 'No'}</ISDEEMEDPOSITIVE>\n"
        f"       <AMOUNT>{amt:.2f}</AMOUNT>\n"
        "      </ALLLEDGERENTRIES.LIST>\n"
    )


def _voucher(t: Transaction, bank_ledger: str, n: int) -> str:
    amount = t.debit or t.credit
    money_out = t.debit > 0
    other = t.ledger or "Suspense A/c"
    vtype = t.voucher_type or ("Payment" if money_out else "Receipt")
    d = t.date.strftime("%Y%m%d")
    narration = t.narration + (f" | Ref: {t.ref}" if t.ref else "")
    if money_out:  # Dr other ledger, Cr bank
        entries = _entry(other, amount, True) + _entry(bank_ledger, amount, False)
    else:  # Dr bank, Cr other ledger
        entries = _entry(bank_ledger, amount, True) + _entry(other, amount, False)
    return (
        '    <TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
        f'     <VOUCHER VCHTYPE="{escape(vtype)}" ACTION="Create">\n'
        f"      <DATE>{d}</DATE>\n"
        f"      <EFFECTIVEDATE>{d}</EFFECTIVEDATE>\n"
        f"      <VOUCHERTYPENAME>{escape(vtype)}</VOUCHERTYPENAME>\n"
        f"      <VOUCHERNUMBER>BTB-{n:05d}</VOUCHERNUMBER>\n"
        f"      <PARTYLEDGERNAME>{escape(other)}</PARTYLEDGERNAME>\n"
        f"      <NARRATION>{escape(narration[:250])}</NARRATION>\n"
        f"{entries}"
        "     </VOUCHER>\n"
        "    </TALLYMESSAGE>\n"
    )


def vouchers_xml(st: Statement, bank_ledger: str, company: str = "") -> str:
    body = "".join(_voucher(t, bank_ledger, i + 1) for i, t in enumerate(st.transactions))
    return _env(body, "Vouchers", company)


def masters_xml(st: Statement, bank_ledger: str, company: str = "") -> str:
    ledgers: dict[str, str] = {bank_ledger: "Bank Accounts"}
    for t in st.transactions:
        name = t.ledger or "Suspense A/c"
        if name == "Cash" or name in ledgers:
            continue  # "Cash" exists by default in every Tally company
        ledgers[name] = ledger_group(name, is_receipt=t.credit > 0)
    body = ""
    for name, group in ledgers.items():
        body += (
            '    <TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
            f'     <LEDGER NAME="{escape(name)}" ACTION="Create">\n'
            f"      <NAME.LIST><NAME>{escape(name)}</NAME></NAME.LIST>\n"
            f"      <PARENT>{escape(group)}</PARENT>\n"
            "     </LEDGER>\n"
            "    </TALLYMESSAGE>\n"
        )
    return _env(body, "All Masters", company)
