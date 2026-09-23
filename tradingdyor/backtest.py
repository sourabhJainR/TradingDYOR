from dataclasses import dataclass
import pandas as pd
import numpy as np

@dataclass
class BacktestResult:
    strategy: str
    cagr: float
    max_drawdown: float
    sharpe: float
    hit_rate: float
    observations: int

def run_signal_backtest(df: pd.DataFrame, signal_col: str, return_col: str) -> BacktestResult:
    x=df[[signal_col,return_col]].dropna().copy()
    if x.empty:
        return BacktestResult(signal_col,0,0,0,0,0)
    position=np.sign(x[signal_col]).shift(1).fillna(0)
    rets=position*x[return_col]
    equity=(1+rets).cumprod()
    years=max(len(rets)/252,1/252)
    cagr=float(equity.iloc[-1]**(1/years)-1)
    dd=float((equity/equity.cummax()-1).min())
    sharpe=float(np.sqrt(252)*rets.mean()/rets.std()) if rets.std() else 0.0
    hit=float((rets>0).mean())
    return BacktestResult(signal_col,cagr,dd,sharpe,hit,len(rets))
