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
from .outcome_learning import DecisionEpisode, OutcomeMemory, evaluate_episode, stable_episode_id
from .market_data import snapshot_ticker
from .market_intelligence import market_intelligence
from .institutional import parse_13f, summarize_positions
from .macro_adapter import live_macro, fred_series
from .sector_adapter import sector_state
from .patents import search_patents
from .decision_fabric import DecisionFabric
from .monthly_optimizer import build_monthly_recommendations

from .research_graph import ResearchGraph
from .orchestrator import ResearchOrchestrator
from .research_collectors import COLLECTORS

app=FastAPI(title="TradingDYOR", version="0.5.0")
policy=RoutingPolicy.load()
experience=ExperienceMemory()
fabric=DecisionFabric(policy, experience)
outcomes=OutcomeMemory()
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
def research_counterfactual(ticker: str, changes: dict[str, dict[str, float]], budget: int = 3):
    snapshot = snapshot_ticker(ticker.upper())
    selected = fabric.select_branches(list(changes), budget=max(1, min(3, budget)))
    selected_changes = {name: changes[name] for name in selected}
    return {"ticker": ticker.upper(), "selected_branches": selected, "branches": [b.__dict__ for b in evaluate_branches(snapshot, selected_changes)]}

@app.get("/research/monthly-recommendations")
def monthly_recommendations(
    market: str = "US",
    tickers: str | None = None,
    benchmark: str | None = None,
):
    selected = [x.strip() for x in tickers.split(",") if x.strip()] if tickers else None
    try:
        return build_monthly_recommendations(market, selected, benchmark)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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

@app.get("/learning/calibration")
def learning_calibration():
    return outcomes.calibration_stats()

@app.get("/learning/outcomes")
def learning_outcomes():
    return {"stats": outcomes.outcome_stats(),
            "pending": [x.__dict__ for x in outcomes.pending()],
            "outcomes": [x.__dict__ for x in outcomes.outcomes[-100:]]}

@app.post("/learning/decision")
def record_decision(payload: dict):
    try:
        episode = DecisionEpisode(**payload)
        outcomes.record_decision(episode)
        return {"recorded": True, "episode_id": episode.id}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))

@app.post("/learning/outcome/{episode_id}/evaluate")
def evaluate_outcome(episode_id: str, benchmark: str | None = "^GSPC"):
    episode=outcomes.get(episode_id)
    if not episode: raise HTTPException(404, "decision episode not found")
    try:
        outcome=evaluate_episode(episode, benchmark=benchmark)
        outcomes.record_outcome(outcome)
        policy.learn_outcome(outcome, episode)
        policy.save()
        return outcome.__dict__
    except Exception as exc:
        raise HTTPException(502, f"outcome evaluation failed: {exc}")

@app.post("/learning/outcomes/evaluate-due")
def evaluate_due_outcomes(benchmark: str | None = "^GSPC"):
    evaluated=[]
    for episode in outcomes.pending():
        try:
            outcome=evaluate_episode(episode, benchmark=benchmark)
            outcomes.record_outcome(outcome)
            policy.learn_outcome(outcome, episode)
            evaluated.append(outcome.__dict__)
        except Exception:
            continue
    if evaluated: policy.save()
    return {"evaluated": len(evaluated), "outcomes": evaluated, "stats": outcomes.outcome_stats()}

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
