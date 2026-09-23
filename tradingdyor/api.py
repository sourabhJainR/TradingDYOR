from fastapi import FastAPI, HTTPException
from .models import SecuritySnapshot
from .decision import decide
from .sources import SOURCES
from .research import rank_universe
from .learning import RoutingPolicy
from .research_engine import research_ticker, research_universe
from .store import count

app=FastAPI(title="TradingDYOR", version="0.2.0")
policy=RoutingPolicy()

@app.get("/health")
def health():
    return {"status":"ok","sources":len(SOURCES),"evidence_records":count()}

@app.get("/sources")
def sources(): return [s.__dict__ for s in SOURCES]

@app.post("/research/score")
def score(snapshot: SecuritySnapshot):
    if not 0 <= snapshot.evidence_coverage <= 1:
        raise HTTPException(400,"evidence_coverage must be between 0 and 1")
    return decide(snapshot).model_dump(mode="json")

@app.post("/research/universe")
def universe(snapshots: list[SecuritySnapshot]):
    if not snapshots: raise HTTPException(400,"at least one snapshot is required")
    return {k:[x.model_dump(mode="json") for x in v] for k,v in rank_universe(snapshots).items()}

@app.get("/research/ticker/{ticker}")
def ticker(ticker: str):
    return research_ticker(ticker.upper())

@app.post("/research/live-universe")
def live_universe(tickers: list[str]):
    if not tickers: raise HTTPException(400,"at least one ticker is required")
    return research_universe([x.upper() for x in tickers[:200]])

@app.get("/learning/policy")
def learning_policy(): return policy.snapshot()
