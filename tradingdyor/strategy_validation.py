from __future__ import annotations

import pandas as pd


def _signal(history: pd.Series, strategy: str) -> int:
    if len(history) < 12:
        return 0
    if strategy == "momentum":
        return int(history.iloc[-1] > history.iloc[-12])
    if strategy == "mean_reversion":
        return int(history.iloc[-1] < history.rolling(12).mean().iloc[-1])
    if strategy == "low_volatility":
        return int(history.pct_change().rolling(12).std().iloc[-1] < history.pct_change().rolling(36).std().iloc[-1])
    raise ValueError(f"unknown strategy: {strategy}")


def walk_forward_strategies(
    prices: pd.Series,
    train_months: int = 12,
    test_months: int = 3,
    strategies: tuple[str, ...] = ("momentum", "mean_reversion", "low_volatility"),
) -> pd.DataFrame:
    p = prices.dropna().sort_index().astype(float)
    if len(p) < train_months + test_months + 12:
        return pd.DataFrame(columns=["date", "strategy", "signal", "forward_return"])
    rows = []
    for i in range(train_months + 12, len(p) - test_months, test_months):
        train_start = max(0, i - train_months)
        train = p.iloc[train_start:i]
        candidates = []
        for strategy in strategies:
            sig = _signal(train, strategy)
            ret = (train.iloc[-1] / train.iloc[0] - 1) * sig
            candidates.append((ret, strategy))
        chosen = max(candidates, key=lambda x: x[0])[1]
        signal = _signal(p.iloc[:i], chosen)
        forward = signal * (p.iloc[i + test_months] / p.iloc[i] - 1)
        rows.append({"date": p.index[i], "strategy": chosen, "signal": signal, "forward_return": forward})
    return pd.DataFrame(rows)


def summarize_strategy_walk_forward(results: pd.DataFrame) -> dict[str, float | str]:
    if results.empty:
        return {"cagr": 0.0, "hit_rate": 0.0, "observations": 0.0, "selected_strategy": ""}
    r = results["forward_return"].fillna(0.0)
    growth = float((1 + r).prod())
    years = max(len(r) / 4, 0.25)
    counts = results["strategy"].value_counts()
    return {
        "cagr": growth ** (1 / years) - 1,
        "hit_rate": float((r > 0).mean()),
        "observations": float(len(r)),
        "selected_strategy": str(counts.index[0]),
    }
