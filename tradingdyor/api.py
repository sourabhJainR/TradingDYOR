from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .models import SecuritySnapshot
from .decision import decide
from .sources import SOURCES
from .research import rank_universe
from .learning import RoutingPolicy
from .research_engine import research_ticker, research_universe
from .store import count
from .filings import sec_filings, filing_signal_tags
from .counterfactual import evaluate_branches
from .strategy_validation import walk_forward_strategies, summarize_strategy_walk_forward
from .experience import Experience, ExperienceMemory
from .market_data import snapshot_ticker
from .market_intelligence import market_intelligence
from .institutional import parse_13f, summarize_positions
from .macro_adapter import live_macro, fred_series
from .sector_adapter import sector_state
from .patents import search_patents
from .decision_fabric import DecisionFabric

from .research_graph import ResearchGraph
from .orchestrator import ResearchOrchestrator
from .research_collectors import COLLECTORS

app=FastAPI(title="TradingDYOR", version="0.5.0")
policy=RoutingPolicy()
experience=ExperienceMemory()
fabric=DecisionFabric(policy, experience)
WEB_ROOT=Path(__file__).resolve().parent.parent / "web"

@app.get("/health")
def health():
    return {"status":"ok","sources":len(SOURCES),"evidence_records":count(),"ui":"spa"}

@app.get("/sources")
def sources(): return [s.__dict__ for s in SOURCES]

@app.get("/")
def spa(): return FileResponse(WEB_ROOT / "index.html")

@app.post("/research/score")
def score(snapshot: SecuritySnapshot):
    if not 0 <= snapshot.evidence_coverage <= 1: raise HTTPException(400,"evidence_coverage must be between 0 and 1")
    return decide(snapshot).model_dump(mode="json")

@app.post("/research/universe")
def universe(snapshots: list[SecuritySnapshot]):
    if not snapshots: raise HTTPException(400,"at least one snapshot is required")
    return {k:[x.model_dump(mode="json") for x in v] for k,v in rank_universe(snapshots).items()}

@app.get("/research/ticker/{ticker}")
def ticker(ticker: str): return research_ticker(ticker.upper())

@app.post("/research/live-universe")
def live_universe(tickers: list[str]):
    if not tickers: raise HTTPException(400,"at least one ticker is required")
    return research_universe([x.upper() for x in tickers[:200]])

@app.get("/research/evidence/{ticker}")
def research_evidence(ticker: str):
    filings = sec_filings(ticker.upper(), limit=20)
    return {
        "ticker": ticker.upper(),
        "filings": [f.__dict__ for f in filings],
        "event_tags": [
            {"form": f.form, "filed": f.filed, "tags": filing_signal_tags(f"{f.form} {f.primary_document}"), "url": f.url}
            for f in filings
        ],
    }

@app.get("/research/market-intelligence/{ticker}")
def research_market_intelligence(ticker: str):
    return market_intelligence(ticker.upper())

@app.get("/research/macro")
def research_macro(series_id: str | None = None):
    data = live_macro()
    if series_id:
        data["fred"] = fred_series(series_id)
    return data

@app.get("/research/sector/{sector}")
def research_sector(sector: str):
    return sector_state(sector)

@app.get("/research/institutional/{manager_cik}")
def research_institutional(manager_cik: str, limit: int = 4):
    positions = parse_13f(manager_cik, max(1, min(limit, 8)))
    return summarize_positions(positions)

@app.post("/research/counterfactual/{ticker}")
def research_counterfactual(ticker: str, changes: dict[str, dict[str, float]]):
    snapshot = snapshot_ticker(ticker.upper())
    return {"ticker": ticker.upper(), "branches": [b.__dict__ for b in evaluate_branches(snapshot, changes)]}

@app.get("/research/backtest/{ticker}")
def research_backtest(ticker: str):
    import yfinance as yf
    history = yf.Ticker(ticker.upper()).history(period="5y", auto_adjust=True)
    if history.empty: raise HTTPException(404, "no price history available")
    results = walk_forward_strategies(history["Close"])
    return {"ticker": ticker.upper(), "summary": summarize_strategy_walk_forward(results),
            "observations": results.to_dict(orient="records")}

@app.get("/learning/experience")
def learning_experience(): return {"stats": experience.capability_stats()}

@app.post("/learning/experience")
def record_experience(payload: dict):
    row = Experience(**payload)
    experience.record(row)
    return {"recorded": True, "stats": experience.capability_stats()}

@app.get("/learning/policy")
def learning_policy(): return policy.snapshot()

@app.get("/learning/plan")
def learning_plan(required_evidence: float = 0.7):
    capabilities=["filings","fundamentals","insiders","earnings","institutional","sector","macro","patents"]
    return fabric.plan(capabilities,max(0,min(1,required_evidence))).__dict__

@app.get("/research/patents/{organization}")
def research_patents(organization: str, limit: int = 25):
    return search_patents(organization, limit)

@app.get("/research/graph/{ticker}")
def research_graph_plan(ticker: str):
    graph = ResearchGraph()
    return ResearchOrchestrator(fabric).plan(graph)

@app.get("/research/run/{ticker}")
def research_run(ticker: str):
    run = ResearchOrchestrator(fabric).run(ticker.upper(), COLLECTORS)
    return run.__dict__
