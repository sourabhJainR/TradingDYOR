# Point-in-Time Evidence Store Contract

TradingDYOR stores external observations in SQLite with separate source-time fields:

- `available_at`: when the fact became available to the historical decision context.
- `published_at`: publisher-declared publication time.
- `observed_at`: time an upstream source/index says it observed the item.
- `retrieved_at`: when TradingDYOR fetched it.
- `as_of`: the observation's legacy capture/reference time; it is not a fallback availability time.

Historical queries select the latest metric whose availability anchor is no later than the requested cutoff. The anchor precedence is `available_at`, then `published_at`, then `observed_at`. Retrieval time and legacy `as_of` are never used to make an item eligible. If all source-time fields are missing, the observation remains stored for provenance but is excluded from point-in-time queries.

The store uses SQLite, a stable observation identity and insert-if-absent semantics so a restart or repeated ingestion does not duplicate the same observation. The schema preserves each original timestamp independently.

Forward-return evaluation defaults to entering on the next trading session after the signal date. Same-day entry is available only as an explicit override because a signal generated after the close cannot safely assume the same close as an executable entry.

## Current scope

This is the persistent storage and query primitive. The one-page brief writes current market metrics, SEC filing observations and news stories into it, and GET /research/history/{ticker}?as_of=... exposes the latest eligible value per metric. The database defaults to `.tradingdyor/point_in_time.sqlite`; set `TRADINGDYOR_PIT_DB` to choose a persistent path on the deployment volume. The local data directory is ignored by Git. Other live collectors are not all wired to write into it yet. Source-specific availability policies, historical universe membership, revised-filing handling, and walk-forward evaluation remain part of the broader issue #19 acceptance.
