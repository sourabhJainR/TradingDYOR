from __future__ import annotations
import pandas as pd

def walk_forward_momentum(prices: pd.Series, train_months: int = 12, test_months: int = 3) -> pd.DataFrame:
    p = prices.dropna().sort_index().astype(float)
    if len(p) < train_months + test_months + 2: return pd.DataFrame(columns=["date", "signal", "forward_return"])
    rows = []
    for i in range(train_months, len(p) - test_months, test_months):
        signal = 1 if p.iloc[:i].pct_change(train_months).iloc[-1] > 0 else 0
        rows.append({"date": p.index[i], "signal": signal, "forward_return": signal * (p.iloc[i + test_months] / p.iloc[i] - 1)})
    return pd.DataFrame(rows)

def summarize_walk_forward(results: pd.DataFrame) -> dict[str, float]:
    if results.empty: return {"cagr": 0.0, "hit_rate": 0.0, "observations": 0.0}
    r = results["forward_return"].fillna(0.0); growth = float((1 + r).prod()); years = max(len(r) / 4, 0.25)
    return {"cagr": growth ** (1 / years) - 1, "hit_rate": float((r > 0).mean()), "observations": float(len(r))}
