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
