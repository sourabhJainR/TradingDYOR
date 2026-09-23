from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class InstitutionalFlow:
    ticker: str
    source: str
    filing_date: str | None
    holder: str
    shares: float | None
    value: float | None

def normalize_flow_rows(ticker: str, rows: list[dict], source: str = "13F") -> list[InstitutionalFlow]:
    return [InstitutionalFlow(ticker.upper(), source, r.get("filing_date"), str(r.get("holder", "")), float(r["shares"]) if r.get("shares") is not None else None, float(r["value"]) if r.get("value") is not None else None) for r in rows]
