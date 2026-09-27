from .models import Decision, SecuritySnapshot
from .strategies import ensemble
from .regime_intelligence import RegimeState, regime_multiplier

def decide(s: SecuritySnapshot, evidence_coverage: float | None = None, provenance: dict | None = None) -> Decision:
    results, raw_score, agreement = ensemble(s)
    regime_name = s.market_regime or "normal"
    regime_state = RegimeState(regime_name, s.regime_score or 0.0, None, None, None, s.regime_stress or 0.0, 0.5, ())
    provisional_action = "BUY" if raw_score >= 0 else "SELL" if raw_score < 0 else "HOLD"
    score = raw_score * regime_multiplier(regime_state, provisional_action)
    event_pressure = min(1.0, max(0.0, s.event_pressure or 0.0))
    coverage=min(1.0, max(0.0, s.evidence_coverage if evidence_coverage is None else evidence_coverage))
    contested=sum(1 for x in (provenance or {}).get("reconciled", []) if x.get("status") == "contested")
    confidence=max(0.0,min(1.0,0.55*agreement+0.45*coverage-0.05*min(5,contested)-0.12*event_pressure-0.08*(s.regime_stress or 0.0)))
    if coverage < 0.40:
        action="HOLD"
    elif score >= 0.25:
        action="BUY"
    elif score <= -0.25:
        action="SELL"
    else:
        action="HOLD"
    reasons=[f"{r.name}: {r.score:+.2f}" for r in results]\n    if s.market_regime:\n        reasons.append(f"market regime: {s.market_regime}, stress={s.regime_stress or 0.0:.2f}")\n    if event_pressure:\n        reasons.append(f"upcoming-event pressure: {event_pressure:.2f}")
    if contested:
        reasons.append(f"{contested} claim conflict(s) require review")
    direction = "upside" if action == "BUY" else "downside" if action == "SELL" else "limited directional edge"
    thesis=f"{action} thesis: the research signals imply {direction} with ensemble score {score:+.2f} and confidence {confidence:.2f}."
    return Decision(
        ticker=s.ticker, action=action, score=score, confidence=confidence,
        evidence_coverage=coverage, strategy_agreement=agreement,
        key_reasons=reasons,
        risks=["Model output is sensitive to stale or incomplete source data", "Conflicting primary-tier evidence reduces confidence" if contested else "Evidence conflicts should be rechecked when sources change"],
        invalidation=["Recompute when evidence coverage or core fundamentals materially change"],
        thesis=thesis,
        strategy_scores={r.name: r.score for r in results},
    )
