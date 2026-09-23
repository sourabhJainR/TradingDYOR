from __future__ import annotations
import pandas as pd
import numpy as np

def backtest_portfolio(prices: pd.DataFrame, weights: dict[str,float], rebalance="M"):
    p=prices[list(weights)].dropna(how="all").ffill().dropna()
    w=pd.Series(weights,dtype=float)
    w=w/w.sum()
    returns=p.pct_change().fillna(0)
    portfolio=(returns*w).sum(axis=1)
    equity=(1+portfolio).cumprod()
    dd=equity/equity.cummax()-1
    years=max(len(equity)/252,1/252)
    cagr=float(equity.iloc[-1]**(1/years)-1)
    vol=float(portfolio.std()*252**0.5)
    sharpe=float(portfolio.mean()*252/vol) if vol else 0.0
    return {
        "cagr":cagr,"max_drawdown":float(dd.min()),
        "volatility":vol,"sharpe":sharpe,
        "final_value":float(equity.iloc[-1]),
        "observations":len(equity),
    }

def compare_strategies(price_map, strategies):
    rows=[]
    for name,weights in strategies.items():
        result=backtest_portfolio(price_map,weights)
        rows.append({"strategy":name,**result})
    return pd.DataFrame(rows).sort_values("cagr",ascending=False).reset_index(drop=True)
