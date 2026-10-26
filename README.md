# BankToBooks

Convert Indian bank statement PDFs (HDFC, SBI, ICICI, Axis, Kotak and most digital e-statements) into
**Excel**, **CSV** and **Tally Prime XML** (ledgers + Payment/Receipt/Contra vouchers).

## Run it

```bash
./run.sh            # first run creates .venv and installs everything
```
Open http://127.0.0.1:8000 and drop in a statement PDF.

## Test it

```bash
./.venv/bin/python tests/make_samples.py   # writes synthetic statements to samples/
./.venv/bin/python tests/evaluate.py       # accuracy report per bank
./.venv/bin/pytest -q                      # full test suite
```
The `samples/` PDFs are fake data generated for testing. `samples/hdfc_locked.pdf` has password `DEMO1234`.

## How it works

| Piece | File |
|---|---|
| Layout-aware parser: finds the table header, maps columns, stitches wrapped narrations | `app/parser/engine.py` |
| Bank detection + account no / IFSC / period | `app/parser/detect.py` |
| Running-balance check (fixes swapped debit/credit, resolves single "Amount" columns, newest-first statements) | `engine._order_and_reconcile` |
| Party name + ledger + voucher-type suggestions | `app/categorize.py` |
| Excel / CSV export | `app/exporters/tabular.py` |
| Tally XML (masters + vouchers) | `app/exporters/tally.py` |
| API (stateless, in-memory) | `app/main.py` |
| Web UI | `app/static/` |

**Privacy:** PDFs are read in memory and discarded; nothing is written to disk or logged. The browser holds
the parsed result and sends it back only when you export.

## Importing into Tally Prime

1. Gateway of Tally → Import → **Masters** → choose `*_tally_ledgers.xml` (once per company).
2. Gateway of Tally → Import → **Transactions** → choose `*_tally_vouchers.xml`.

Rows the app couldn't categorise go to **Suspense A/c** — set the ledger in the app before exporting
(setting it on one row fills every other row from the same party).

## Known limits / next steps

- Scanned (image) statements need OCR — planned via Claude vision as a paid feature.
- Tune against real statements from each bank (layouts vary by download channel).
- Accounts + usage limits + Razorpay billing.
- Remember party → ledger mappings per customer.

## Deploy (free, Render)

1. Push this folder to a **private** GitHub repo (VS Code: Source Control → Publish to GitHub).
2. render.com → New → **Blueprint** → select the repo. `render.yaml` sets everything up.
3. Free plan sleeps after 15 min idle; the first request after that takes ~1 minute.

Real statements go in `samples/real/` — PDFs are git-ignored and never pushed.
