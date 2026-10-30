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


## Partial research and provider failures

The one-page brief uses the ResearchGraph and ResearchOrchestrator rather than a monolithic collector. Provider tasks execute independently. A provider failure is terminal evidence for that task, not a reason to discard successful sibling results. Synthesis runs after selected dependencies reach a terminal state (completed, failed or skipped), records missing and skipped tasks separately, and marks the result partial when a selected task failed or did not complete. Evidence coverage and confidence are capped by the fraction of selected source tasks that completed. If the fundamental snapshot is unavailable, the API returns an explicit HOLD/unavailable result rather than fabricating a company thesis.

Intentional capability skips do not count as provider failures. Missing publication time is not inferred from retrieval time. These contracts are covered by deterministic tests; live provider coverage still needs operational monitoring.
