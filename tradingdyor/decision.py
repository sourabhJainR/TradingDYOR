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
    confidence=max(0.0,min(1.0,0.55*agreement+0.45*coverage-0.05*min(5,contested)-0.12*event_pressure-0.08*(s.regime_stress or 0.0)-0.10*(s.macro_pressure or 0.0)))
    news_status = s.news_sentiment_status
    news_score = s.news_sentiment_score
    news_confidence = max(0.0, min(1.0, s.news_sentiment_confidence or 0.0))
    news_disagrees = (
        news_status == "scored" and news_score is not None
        and abs(raw_score) >= 0.05
        and ((raw_score > 0 and news_score < 0) or (raw_score < 0 and news_score > 0))
    )
    if news_disagrees:
        # News tone is contextual evidence only. It can lower confidence when
        # it conflicts with fundamentals, but it never changes the directional score.
        confidence = max(0.0, confidence - 0.05 * news_confidence)
    if coverage < 0.40:
        action="HOLD"
    elif score >= 0.25:
        action="BUY"
    elif score <= -0.25:
        action="SELL"
    else:
        action="HOLD"
    reasons=[f"{r.name}: {r.score:+.2f}" for r in results]
    if s.macro_status == "available" and s.market_regime:
        reasons.append(f"market regime: {s.market_regime}, stress={s.regime_stress or 0.0:.2f}")
    else:
        reasons.append("macro regime unavailable; no macro adjustment applied")
    if s.event_status == "available":
        reasons.append(f"tracked event pressure: {event_pressure:.2f}")
    elif s.event_status == "empty":
        reasons.append("no tracked event forecasts; event risk remains unknown")
    else:
        reasons.append("event forecast data unavailable; no event adjustment applied")
    if contested:
        reasons.append(f"{contested} claim conflict(s) require review")
    if news_status == "scored" and news_score is not None:
        reasons.append(
            f"news tone: {news_score:+.2f} across {s.news_sample_count} articles/"
            f"{s.news_publisher_count} publishers; context only"
        )
        if news_disagrees:
            reasons.append("news tone conflicts with the fundamental signal; confidence reduced")
    else:
        reasons.append(
            f"news sentiment unscored ({s.news_sample_count} articles/"
            f"{s.news_publisher_count} publishers); no sentiment adjustment"
        )
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
