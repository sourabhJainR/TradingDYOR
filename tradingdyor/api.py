from fastapi import FastAPI, HTTPException
from .models import SecuritySnapshot
from .decision import decide
from .sources import SOURCES

app=FastAPI(title="TradingDYOR", version="0.1.0")

@app.get("/health")
def health(): return {"status":"ok","sources":len(SOURCES)}

@app.get("/sources")
def sources(): return [s.__dict__ for s in SOURCES]

@app.post("/research/score")
def score(snapshot: SecuritySnapshot):
    if snapshot.evidence_coverage < 0:
        raise HTTPException(400,"invalid evidence coverage")
    return decide(snapshot).model_dump(mode="json")
