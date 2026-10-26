from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Transaction:
    date: date
    narration: str = ""
    ref: str = ""
    value_date: Optional[date] = None
    debit: float = 0.0
    credit: float = 0.0
    balance: Optional[float] = None
    # enrichment
    party: str = ""
    ledger: str = ""
    voucher_type: str = ""
    reconciled: Optional[bool] = None
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["value_date"] = self.value_date.isoformat() if self.value_date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        d = dict(d)
        d["date"] = date.fromisoformat(d["date"])
        if d.get("value_date"):
            d["value_date"] = date.fromisoformat(d["value_date"])
        else:
            d["value_date"] = None
        for k in ("debit", "credit"):
            d[k] = float(d.get(k) or 0)
        if d.get("balance") not in (None, ""):
            d["balance"] = float(d["balance"])
        else:
            d["balance"] = None
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class Statement:
    bank: str = "Unknown"
    account_number: str = ""
    ifsc: str = ""
    account_holder: str = ""
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    transactions: list[Transaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: int = 0

    @property
    def total_debit(self) -> float:
        return round(sum(t.debit for t in self.transactions), 2)

    @property
    def total_credit(self) -> float:
        return round(sum(t.credit for t in self.transactions), 2)

    @property
    def reconciled_pct(self) -> float:
        checked = [t for t in self.transactions if t.reconciled is not None]
        if not checked:
            return 0.0
        return round(100.0 * sum(1 for t in checked if t.reconciled) / len(checked), 1)

    def to_dict(self) -> dict:
        return {
            "bank": self.bank,
            "account_number": self.account_number,
            "ifsc": self.ifsc,
            "account_holder": self.account_holder,
            "period_from": self.period_from.isoformat() if self.period_from else None,
            "period_to": self.period_to.isoformat() if self.period_to else None,
            "opening_balance": self.opening_balance,
            "closing_balance": self.closing_balance,
            "total_debit": self.total_debit,
            "total_credit": self.total_credit,
            "count": len(self.transactions),
            "reconciled_pct": self.reconciled_pct,
            "pages": self.pages,
            "warnings": self.warnings,
            "transactions": [t.to_dict() for t in self.transactions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Statement":
        s = cls(
            bank=d.get("bank", "Unknown"),
            account_number=d.get("account_number", ""),
            ifsc=d.get("ifsc", ""),
            account_holder=d.get("account_holder", ""),
            opening_balance=d.get("opening_balance"),
            closing_balance=d.get("closing_balance"),
        )
        if d.get("period_from"):
            s.period_from = date.fromisoformat(d["period_from"])
        if d.get("period_to"):
            s.period_to = date.fromisoformat(d["period_to"])
        s.transactions = [Transaction.from_dict(t) for t in d.get("transactions", [])]
        return s
