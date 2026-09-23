from .models import Decision, SecuritySnapshot
from .strategies import ensemble

def decide(s: SecuritySnapshot) -> Decision:
    results, score, agreement = ensemble(s)
    coverage=min(1.0,s.evidence_coverage)
    confidence=max(0.0,min(1.0,0.55*agreement+0.45*coverage))
    if coverage < 0.40:
        action="HOLD"
    elif score >= 0.25:
        action="BUY"
    elif score <= -0.25:
        action="SELL"
    else:
        action="HOLD"
    reasons=[f"{r.name}: {r.score:+.2f}" for r in results]
    return Decision(
        ticker=s.ticker, action=action, score=score, confidence=confidence,
        evidence_coverage=coverage, strategy_agreement=agreement,
        key_reasons=reasons,
        risks=["Model output is sensitive to stale or incomplete source data"],
        invalidation=["Recompute when evidence coverage or core fundamentals materially change"],
    )
