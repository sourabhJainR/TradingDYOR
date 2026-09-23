from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class EarningsObservation:
    ticker: str
    period: str
    reported: float | None
    estimate: float | None
    surprise_pct: float | None
    guidance: str = ""

def earnings_signal(rows: list[EarningsObservation]) -> dict[str,float]:
    valid=[r for r in rows if r.surprise_pct is not None]
    avg=sum(r.surprise_pct for r in valid)/len(valid) if valid else 0.0
    positive=sum(r.surprise_pct>0 for r in valid)/len(valid) if valid else 0.0
    return {"avg_surprise_pct":avg,"positive_rate":positive,"observations":float(len(valid))}
