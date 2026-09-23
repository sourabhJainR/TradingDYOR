from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Regime:
    name: str
    score: float
    drivers: tuple[str, ...]

def classify_regime(spy_return: float | None, vol: float | None, rates: float | None) -> Regime:
    if spy_return is None and vol is None and rates is None: return Regime("unknown", 0.0, ())
    score = 0.0; drivers = []
    if spy_return is not None: score += 0.4 if spy_return > 0 else -0.4; drivers.append("equity trend")
    if vol is not None: score += -0.3 if vol > 0.30 else 0.2; drivers.append("realized volatility")
    if rates is not None: score += -0.2 if rates > 0.05 else 0.1; drivers.append("policy-rate pressure")
    name = "risk-on" if score >= 0.25 else "risk-off" if score <= -0.25 else "mixed"
    return Regime(name, max(-1.0, min(1.0, score)), tuple(drivers))
