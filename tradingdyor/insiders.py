from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class InsiderTransaction:
    ticker: str
    filing_date: str
    insider: str
    form: str
    shares: float | None
    price: float | None
    transaction_code: str

def normalize_insider_rows(ticker: str, rows: list[dict]) -> list[InsiderTransaction]:
    return [InsiderTransaction(ticker.upper(),str(r.get("filing_date","")),str(r.get("insider","")),str(r.get("form","4")),float(r["shares"]) if r.get("shares") is not None else None,float(r["price"]) if r.get("price") is not None else None,str(r.get("transaction_code",""))) for r in rows]

def insider_signal(rows: list[InsiderTransaction]) -> dict[str,float]:
    buys=sum((r.shares or 0) for r in rows if r.transaction_code in {"P","A"})
    sells=sum((r.shares or 0) for r in rows if r.transaction_code in {"S","D"})
    total=buys+sells
    return {"buy_shares":buys,"sell_shares":sells,"net_shares":buys-sells,"buy_sell_ratio":buys/sells if sells else (buys if buys else 0.0)}
