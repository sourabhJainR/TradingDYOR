from __future__ import annotations
from .market_data import snapshot_ticker
from .decision import decide

def research_ticker(ticker: str):
    snapshot=snapshot_ticker(ticker)
    decision=decide(snapshot)
    return {"snapshot":snapshot.model_dump(mode="json"),"decision":decision.model_dump(mode="json")}

def research_universe(tickers: list[str]):
    results=[]
    for ticker in dict.fromkeys(tickers):
        try:
            results.append(research_ticker(ticker))
        except Exception as exc:
            results.append({"ticker":ticker,"error":str(exc)})
    valid=[r["decision"] for r in results if "decision" in r]
    return {
        "results":results,
        "buy":sorted([x for x in valid if x["action"]=="BUY"],key=lambda x:x["score"],reverse=True)[:5],
        "hold":sorted([x for x in valid if x["action"]=="HOLD"],key=lambda x:x["score"],reverse=True)[:5],
        "sell":sorted([x for x in valid if x["action"]=="SELL"],key=lambda x:x["score"])[:5],
    }
