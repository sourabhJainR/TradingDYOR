# Next phase: evidence-driven research engine

The v0.2 engine adds point-in-time observations, live market snapshots, a persistent evidence ledger, portfolio backtesting primitives and live single/universe research APIs.

## Data boundary

Market-data fields are inputs, not evidence by themselves. Public-source browser observations and filings are stored separately so the system can show exactly what was observed and when.

## Backtest boundary

Historical signals must be generated from data available at the signal timestamp. Forward returns are measured only after that timestamp. This prevents look-ahead leakage.

## Production expansion

Source-specific parsers should populate:
- SEC filings and filing dates
- quarterly/yearly financial statements
- insider transactions
- institutional ownership and 13F changes
- earnings/guidance
- corporate actions
- M&A, litigation and patents
- macro/sector indicators

The strategy layer should then consume point-in-time features rather than current snapshots.

The monthly workflow should score prior decisions, update routing/verification policy, rerun walk-forward validation and record model/version changes.
