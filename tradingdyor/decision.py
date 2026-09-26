from .models import Decision, SecuritySnapshot
from .strategies import ensemble


def decide(s: SecuritySnapshot, evidence_coverage: float | None = None, provenance: dict | None = None) -> Decision:
    results, score, agreement = ensemble(s)
    coverage=min(1.0, max(0.0, s.evidence_coverage if evidence_coverage is None else evidence_coverage))
    contested=sum(1 for x in (provenance or {}).get("reconciled", []) if x.get("status") == "contested")
    confidence=max(0.0,min(1.0,0.55*agreement+0.45*coverage-0.05*min(5,contested)))
    if coverage < 0.40:
        action="HOLD"
    elif score >= 0.25:
        action="BUY"
    elif score <= -0.25:
        action="SELL"
    else:
        action="HOLD"
    reasons=[f"{r.name}: {r.score:+.2f}" for r in results]
    if contested:
        reasons.append(f"{contested} claim conflict(s) require review")
    return Decision(
        ticker=s.ticker, action=action, score=score, confidence=confidence,
        evidence_coverage=coverage, strategy_agreement=agreement,
        key_reasons=reasons,
        risks=["Model output is sensitive to stale or incomplete source data", "Conflicting primary-tier evidence reduces confidence" if contested else "Evidence conflicts should be rechecked when sources change"],
        invalidation=["Recompute when evidence coverage or core fundamentals materially change"],
    )
