# TradingDYOR architecture

## Evidence model

A Source is a registered public endpoint. An Evidence record is an immutable observation containing source, retrieval time, title, excerpt, content hash and extraction method. A SecuritySnapshot is a point-in-time feature set. A Signal records one strategy's output. A Decision records the final auditable output.

## Decision Fabric

The Decision Fabric learns four policies from historical outcomes:
1. capability selection: which collector/model is useful
2. verification depth: how much independent evidence is required
3. retry/escalation: when a weak route should trigger another route
4. research branch selection: which hypothesis deserves deeper investigation

Learning never mutates raw evidence. Policies are updated only from realized outcomes.

## Research loop

1. Collect current observations.
2. Normalize point-in-time features.
3. Run independent strategies.
4. Backtest each strategy out of sample.
5. Ensemble strategies that pass validation gates.
6. Produce an evidence table and uncertainty.
7. Persist the decision and invalidation triggers.
8. Reassess monthly.
9. Score prior decisions against realized outcomes.
10. Update routing and strategy weights.

Backtests must use only information available at the historical signal timestamp. No future fundamentals may leak into a prior snapshot.

The UI exposes model outputs as Buy/Hold/Sell buckets with evidence coverage, model agreement, valuation context, key risks and invalidation triggers.


## Macro, regime and event intelligence

The decision loop now has a separate context layer for:
- market slowdowns, high-stress periods and crisis regimes detected from long-history volatility, drawdown, trend and VIX;
- historical extreme-event anchors including the global financial crisis, euro-area stress, COVID shock, inflation/rate shock and regional-bank stress;
- fiscal deficit, sovereign debt, policy rates, long rates, FX, dollar conditions, credit stress, growth and inflation indicators where a verified series is available;
- upcoming geopolitical, government, macro, sector and company events represented as time-bounded forecasts rather than unverified narratives;
- advance-tax and direct-tax collection observations as a leading macro/corporate-profit signal for India. The system stores published aggregate observations only; it does not access confidential taxpayer filings;
- post-event learning: actual event time, surprise and market reaction are stored against the forecast, allowing timing error and directional accuracy to be measured.

A stressed regime changes the required evidence threshold and scales the decision score rather than blindly suppressing all opportunities. This preserves the ability to find positive expected-return trades during weak markets while reducing confidence when historical adverse movement is elevated.

The event loop is:
forecast -> expected window -> observation -> surprise -> market reaction -> timing error -> calibration -> future event weighting.

This is intentionally separated from the raw evidence ledger so learning cannot rewrite historical facts.
