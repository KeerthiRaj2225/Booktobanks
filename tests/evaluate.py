"""Compare parser output against the synthetic truth files: python tests/evaluate.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.parser.engine import parse_pdf
from app.categorize import categorize

S = Path(__file__).resolve().parent.parent / "samples"

def score(pdf: Path, password=None):
    truth = json.loads(pdf.with_suffix(".truth.json").read_text())
    st = categorize(parse_pdf(pdf.read_bytes(), password))
    tt = truth["transactions"]
    got = st.transactions
    exact = sum(1 for a, b in zip(got, tt)
                if a.date.isoformat() == b["date"] and abs(a.debit - b["debit"]) < .01
                and abs(a.credit - b["credit"]) < .01 and a.balance is not None and abs(a.balance - b["balance"]) < .01)
    narr = sum(1 for a, b in zip(got, tt) if a.narration.replace(" ", "") == b["narration"].replace(" ", ""))
    party = sum(1 for a, b in zip(got, tt) if a.party.upper() == b["party"])
    return dict(file=pdf.name, bank=st.bank, rows=f"{len(got)}/{len(tt)}", exact=exact, narration=narr, party=party,
                reconciled=st.reconciled_pct, opening_ok=st.opening_balance is not None and abs(st.opening_balance-truth["opening"])<.01,
                warnings=st.warnings)

if __name__ == "__main__":
    for p in sorted(S.glob("*.pdf")):
        r = score(p, "DEMO1234" if "locked" in p.name else None)
        print(json.dumps(r))
