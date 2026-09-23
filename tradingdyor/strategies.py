from dataclasses import dataclass
import numpy as np
from .models import SecuritySnapshot

@dataclass(frozen=True)
class StrategyResult:
    name: str
    score: float
    reasons: list[str]

def _clip(x, lo=-1.0, hi=1.0):
    return float(np.clip(x, lo, hi))

def quality_growth(s: SecuritySnapshot) -> StrategyResult:
    parts=[]
    if s.revenue_growth is not None: parts.append(("growth", _clip(s.revenue_growth / 0.30)))
    if s.earnings_growth is not None: parts.append(("earnings", _clip(s.earnings_growth / 0.35)))
    if s.roe is not None: parts.append(("roe", _clip((s.roe-0.10)/0.20)))
    score=float(np.mean([v for _,v in parts])) if parts else 0.0
    return StrategyResult("quality_growth",score,[f"{k}={v:.2f}" for k,v in parts])

def value_quality(s: SecuritySnapshot) -> StrategyResult:
    parts=[]
    if s.pe is not None and s.pe > 0: parts.append(("pe", _clip((25-s.pe)/25)))
    if s.ps is not None and s.ps > 0: parts.append(("ps", _clip((8-s.ps)/8)))
    if s.roe is not None: parts.append(("roe", _clip((s.roe-0.08)/0.22)))
    score=float(np.mean([v for _,v in parts])) if parts else 0.0
    return StrategyResult("value_quality",score,[f"{k}={v:.2f}" for k,v in parts])

def momentum(s: SecuritySnapshot) -> StrategyResult:
    m=_clip((s.momentum_12m or 0)/0.50)
    v=_clip(1-(s.volatility_90d or 0)/0.80)
    return StrategyResult("momentum",float((m+v)/2),[f"momentum={m:.2f}",f"volatility={v:.2f}"])

def risk_adjusted(s: SecuritySnapshot) -> StrategyResult:
    growth=_clip((s.earnings_growth or 0)/0.40)
    debt=_clip(1-(s.debt_to_equity or 0)/2.0)
    vol=_clip(1-(s.volatility_90d or 0)/0.80)
    return StrategyResult("risk_adjusted",float(np.mean([growth,debt,vol])),[f"growth={growth:.2f}",f"debt={debt:.2f}",f"vol={vol:.2f}"])

STRATEGIES=(quality_growth,value_quality,momentum,risk_adjusted)

def ensemble(s: SecuritySnapshot):
    results=[fn(s) for fn in STRATEGIES]
    scores=np.array([r.score for r in results])
    return results,float(scores.mean()),float(1-scores.std())
