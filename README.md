# TradingDYOR

Evidence-first, continuously evaluated equity research and decision-support platform.

It combines:
- 50 public research sources and filings
- browser collection through Experts.js + Playwright
- structured evidence with source URL, timestamp, excerpt and confidence
- market, financial, macro, ownership, insider, catalyst and risk features
- multi-strategy backtesting
- an adaptive Decision Fabric that learns routing, verification depth, retry policy and research-branch selection
- an interactive Streamlit dashboard
- monthly reassessment rather than static recommendations

Python owns data, scoring, backtesting and APIs. Node.js + Experts.js + Playwright owns browser research and specialist-agent orchestration.

Pipeline:
`sources -> browser/API collection -> evidence ledger -> features -> strategy ensemble -> backtest -> Decision Fabric -> evidence report -> UI`

The system separates observed facts from model interpretation. A recommendation is gated by evidence freshness and coverage.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn tradingdyor.api:app --reload
```

```bash
cd agents
npm install
npx playwright install chromium
node src/runner.js --url https://www.berkshirehathaway.com/letters/letters.html
```

```bash
streamlit run tradingdyor/dashboard.py
```

See `docs/architecture.md` for the data model and learning loop.

This is research decision support, not a guarantee of returns or personalized investment advice.


## 30-day time-bound trade planning

The API endpoint `/research/monthly-recommendations?market=US` or `market=INDIA` evaluates a selected universe for a maximum 30-day trade horizon. It selects stop-loss, take-profit and holding-period parameters from historical training data, holds out the most recent 63 trading days for validation, and returns explicit entry, target, stop and time-stop levels.

This is an optimization and research framework, not a guarantee of maximum future return. The engine rejects a BUY when its current momentum gate and recent out-of-sample evidence do not support a positive one-month trade case.


## One-page stock brief

The interactive screener links each selected ticker to `/brief/{ticker}`. The brief combines company fundamentals, the current recommendation, filing/earnings/insider/corporate-action observations, and GDELT news. News stories include source links, retrieval/seen timestamps, event labels, and duplicate-story grouping. GDELT tone is shown only when the article sample and publisher diversity meet minimum thresholds; otherwise sentiment is explicitly unscored.

API:
- `GET /research/brief/{ticker}` — one-page JSON research contract.
- `GET /research/news/{ticker}?timespan=7d&limit=25` — news and cautious sentiment observations.
- `GET /brief/{ticker}` — responsive one-page UI.

The news adapter does not infer publication time from GDELT's seen time. Missing publication timestamps remain null. The one-page brief runs its company collectors through the research graph: successful providers remain visible when another provider fails, the synthesis is marked partial, and evidence coverage/confidence are capped by completed selected tasks. This first slice does not yet provide a full-market screener or independently verified news coverage; use explicit ticker universes and treat unavailable provider data as unknown. No trade execution is supported.
