"""
BankToBooks API.

Privacy by design: uploaded PDFs are processed in memory and never written to disk or logged.
The browser keeps the parsed result and sends it back for exports, so the server is stateless.

Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .categorize import RULES, SUSPENSE, categorize
from .exporters.tabular import to_csv, to_excel
from .exporters.tally import masters_xml, vouchers_xml
from .parser.detect import detect_bank
from .parser.engine import NoTextLayer, PasswordRequired, TableNotFound, WrongPassword, parse_pdf
from .parser.models import Statement

MAX_BYTES = 15 * 1024 * 1024
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="BankToBooks", version="0.1.0", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ledgers")
def ledgers():
    names = sorted({r[1] for r in RULES} | {SUSPENSE[0]})
    return {"ledgers": names, "voucher_types": ["Payment", "Receipt", "Contra", "Journal"]}


@app.post("/api/convert")
async def convert(file: UploadFile = File(...), password: Optional[str] = Form(None)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        return _err(413, "too_large", "File is larger than 15 MB.")
    if not data.startswith(b"%PDF"):
        return _err(415, "not_pdf", "Please upload a PDF bank statement.")
    try:
        st = parse_pdf(data, password or None)
    except PasswordRequired:
        return _err(401, "password_required", "This statement is password protected. Enter the PDF password.")
    except WrongPassword:
        return _err(401, "wrong_password", "That password didn't work. Banks usually use a mix of your name and date of birth or customer ID.")
    except NoTextLayer:
        return _err(422, "scanned", "This looks like a scanned/photo PDF. Scanned statements are coming soon - please download the e-statement from net banking.")
    except TableNotFound:
        return _err(422, "no_table", "We couldn't find a transactions table in this PDF.")
    except Exception:  # never echo statement contents back in errors
        return _err(500, "parse_failed", "Something went wrong reading this PDF. Please try another statement.")
    finally:
        del data

    categorize(st)
    _, default_ledger = detect_bank(st.bank.upper())
    out = st.to_dict()
    out["default_bank_ledger"] = default_ledger
    return out


class ExportRequest(BaseModel):
    statement: dict
    bank_ledger: str = "Bank A/c"
    company: str = ""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "statement"


@app.post("/api/export/{fmt}")
def export(fmt: str, req: ExportRequest):
    try:
        st = Statement.from_dict(req.statement)
    except Exception:
        raise HTTPException(400, "Invalid statement data")
    base = _safe(f"{st.bank}_{st.account_number[-4:] if st.account_number else ''}_{date.today():%Y%m%d}")
    if fmt == "xlsx":
        return Response(
            to_excel(st, req.bank_ledger),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'},
        )
    if fmt == "csv":
        return Response(to_csv(st), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'})
    if fmt == "tally-vouchers":
        return Response(vouchers_xml(st, req.bank_ledger, req.company), media_type="application/xml",
                        headers={"Content-Disposition": f'attachment; filename="{base}_tally_vouchers.xml"'})
    if fmt == "tally-masters":
        return Response(masters_xml(st, req.bank_ledger, req.company), media_type="application/xml",
                        headers={"Content-Disposition": f'attachment; filename="{base}_tally_ledgers.xml"'})
    raise HTTPException(404, "Unknown export format")
