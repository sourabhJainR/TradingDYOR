# Outcome Learning

TradingDYOR now closes the research loop:

Decision -> predicted thesis -> time-bound outcome -> realized return/risk -> attribution -> learning -> recalibration.

Each decision becomes a DecisionEpisode containing:
- decision timestamp and entry price
- BUY/SELL/HOLD action and explicit thesis
- strategy scores
- research sources and capabilities used
- verification depth
- evaluation horizon

When the horizon expires, evaluate_episode records realized return, maximum favorable/adverse movement, optional benchmark excess return, directional/thesis hit, and bounded attribution signals.

The outcome learner updates capability weights, strategy/source learning signals, verification depth, and retry/routing behavior. Learning is gated by resolved outcomes and persisted in .tradingdyor/policy.json. Decision/outcome episodes are persisted in .tradingdyor/outcomes.json.

Attribution represents alignment with the realized outcome, not a causal claim that a source or capability caused a return. No learning update occurs until an outcome is resolved.

API:
- GET /learning/outcomes
- POST /learning/decision
- POST /learning/outcome/{episode_id}/evaluate
- POST /learning/outcomes/evaluate-due
- GET /learning/policy
- GET /learning/calibration

The research orchestrator automatically creates a 30-day episode when it produces a valid decision with a usable price.


## Calibration

Outcome calibration is sample-aware. Strategy, source, and capability statistics expose observation count, directional hit rate, shrinkage toward a neutral prior, benchmark-relative return, adverse excursion, risk rate, horizon-specific quality, and a confidence signal. RoutingPolicy reduces its update rate as observations accumulate so early outcomes do not dominate later evidence.

Outcome horizons are evaluated by calendar time and then aligned to the first available trading observation on or after the target date.
