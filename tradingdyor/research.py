from .models import SecuritySnapshot
from .decision import decide

def rank_universe(snapshots: list[SecuritySnapshot]):
    decisions=[decide(s) for s in snapshots]
    buys=sorted((d for d in decisions if d.action=="BUY"),key=lambda x:(x.score,x.confidence),reverse=True)[:5]
    holds=sorted((d for d in decisions if d.action=="HOLD"),key=lambda x:(x.score,x.confidence),reverse=True)[:5]
    sells=sorted((d for d in decisions if d.action=="SELL"),key=lambda x:(x.score,x.confidence))[:5]
    return {"buy":buys,"hold":holds,"sell":sells}
