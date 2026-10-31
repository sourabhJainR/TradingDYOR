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


## Multi-source news

The brief queries GDELT DOC and Google News RSS with a bounded timeout and at most two concurrent provider calls. A single provider failure returns partial results from the other source; failures are reported by provider without exposing exception messages. Stories are grouped across sources by normalized title while retaining publisher domains, source URLs and provider identities.

GDELT seen time and Google News RSS publication time remain separate fields. Retrieval time is recorded at the aggregate response level and is not used as a substitute for publication/availability time. Only GDELT's article tone contributes to the sentiment aggregate; Google News headlines are not assigned synthetic sentiment. Sentiment remains unscored below the five-story / three-publisher threshold.

This is not a full independent fact-check: publisher and article links are preserved for review, and conflicting coverage still requires explicit claim reconciliation. Google News RSS availability and regional relevance require live operational monitoring.


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


## Bounded market screener

The screener discovers US listed equity candidates from Nasdaq Trader symbol directories and India EQ-series candidates from NSE's equity list. It caches each universe for 24 hours, filters test issues and ETFs, and screens up to 12 symbols per request. Snapshot fan-out is bounded by a shared 15-second deadline, a process-wide eight-worker pool and a 16-slot in-flight ceiling. The screener returns partial results for stale universes, provider timeouts, capacity limits and unavailable metrics; it never treats a missing metric as a passing filter.

Filters include market capitalization, P/E, revenue and earnings growth, ROE, debt/equity, 12-month momentum, 90-day volatility, dividend yield, average volume and sector. A candidate is linked to the same ticker's one-page brief.

The exchange directory is a candidate universe, not a complete security master. It does not yet include a point-in-time archive of historical universe membership or guarantee that every security has a complete Yahoo Finance snapshot. The screener is advisory-only and does not execute trades.

## Source timestamp contract

The one-page company snapshot keeps `retrieved_at` separate from `price_as_of`. Price, momentum and volatility observations may enter point-in-time history only when the source market-data timestamp is known. Fundamentals with only a retrieval timestamp remain visible in the current brief but are not treated as historically available. GDELT seen time and Google News publication time remain separate. News sentiment can lower confidence when it conflicts with fundamentals, but it cannot change the directional score; low-sample sentiment remains unscored.
