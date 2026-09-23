from __future__ import annotations
import yfinance as yf
from .sector import SectorState, sector_score
SECTOR_ETFS={"Technology":"XLK","Communication Services":"XLC","Consumer Cyclical":"XLY","Consumer Defensive":"XLP","Financial Services":"XLF","Healthcare":"XLV","Industrials":"XLI","Energy":"XLE","Utilities":"XLU","Real Estate":"XLRE","Basic Materials":"XLB"}
def sector_state(sector):
    etf=SECTOR_ETFS.get(sector)
    if not etf: return {"sector":sector,"status":"unmapped"}
    try:
        h=yf.Ticker(etf).history(period="1y",auto_adjust=True)["Close"].dropna()
        r1=float(h.iloc[-1]/h.iloc[-22]-1) if len(h)>22 else 0.0; r6=float(h.iloc[-1]/h.iloc[-127]-1) if len(h)>127 else r1
        vol=float(h.pct_change().dropna().tail(63).std()*252**0.5) if len(h)>63 else 0.0
        breadth=max(0.0,min(1.0,0.5+0.5*r1/0.10)); state=SectorState(sector,r1,r6,vol,breadth,"trend")
        return {"sector":sector,"etf":etf,"score":sector_score(state),"state":state.__dict__}
    except Exception as exc: return {"sector":sector,"etf":etf,"status":"error","error":str(exc)}
