from fastapi import FastAPI, HTTPException
from .models import SecuritySnapshot
from .decision import decide
from .sources import SOURCES
from .research import rank_universe
from .learning import RoutingPolicy

app=FastAPI(title="TradingDYOR", version="0.1.0")
policy=RoutingPolicy()

@app.get("/health")
def health(): return {"status":"ok","sources":len(SOURCES)}

@app.get("/sources")
def sources(): return [s.__dict__ for s in SOURCES]

@app.post("/research/score")
def score(snapshot: SecuritySnapshot):
    if not 0 <= snapshot.evidence_coverage <= 1:
        raise HTTPException(400,"evidence_coverage must be between 0 and 1")
    return decide(snapshot).model_dump(mode="json")

@app.post("/research/universe")
def universe(snapshots: list[SecuritySnapshot]):
    if not snapshots:
        raise HTTPException(400,"at least one snapshot is required")
    return {k:[x.model_dump(mode="json") for x in v] for k,v in rank_universe(snapshots).items()}

@app.get("/learning/policy")
def learning_policy(): return policy.snapshot()
