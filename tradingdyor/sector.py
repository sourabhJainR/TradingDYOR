from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SectorState:
    sector: str
    return_1m: float
    return_6m: float
    volatility: float
    breadth: float
    regime: str

def sector_score(s: SectorState) -> float:
    return 0.35*s.return_1m + 0.35*s.return_6m + 0.15*s.breadth - 0.15*s.volatility
