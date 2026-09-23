from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CorporateAction:
    ticker: str
    event_date: str
    kind: str
    ratio: float | None = None
    cash: float | None = None

def normalize_actions(rows: list[dict]) -> list[CorporateAction]:
    return [CorporateAction(str(r.get("ticker","")).upper(),str(r.get("event_date","")),str(r.get("kind","")),float(r["ratio"]) if r.get("ratio") is not None else None,float(r["cash"]) if r.get("cash") is not None else None) for r in rows]
