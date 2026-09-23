from __future__ import annotations
from dataclasses import asdict
import math, os, requests
import yfinance as yf
from .macro import classify_regime
def _close(ticker,period="1y"):
    try: return yf.Ticker(ticker).history(period=period,auto_adjust=True)["Close"].dropna()
    except Exception: return None
def live_macro():
    spy,vix,tnx=_close("SPY"),_close("^VIX"),_close("^TNX")
    spy_return=float(spy.iloc[-1]/spy.iloc[-21]-1) if spy is not None and len(spy)>21 else None
    vol=float(spy.pct_change().dropna().tail(63).std()*math.sqrt(252)) if spy is not None and len(spy)>63 else None
    vix_level=float(vix.iloc[-1]/100) if vix is not None and len(vix) else None
    rate=float(tnx.iloc[-1]/100) if tnx is not None and len(tnx) else None
    regime=classify_regime(spy_return,vol,rate)
    return {"spy_1m_return":spy_return,"realized_vol_3m":vol,"vix":vix_level,"10y_proxy":rate,"regime":asdict(regime),"sources":["Yahoo Finance SPY","Yahoo Finance ^VIX","Yahoo Finance ^TNX"]}
def fred_series(series_id,api_key=None,limit=120):
    key=api_key or os.getenv("FRED_API_KEY")
    if not key: return {"series_id":series_id,"status":"not_configured","observations":[]}
    r=requests.get("https://api.stlouisfed.org/fred/series/observations",params={"series_id":series_id,"api_key":key,"file_type":"json","limit":limit,"sort_order":"desc"},timeout=20); r.raise_for_status()
    return {"series_id":series_id,"status":"ok","observations":r.json().get("observations",[])}
