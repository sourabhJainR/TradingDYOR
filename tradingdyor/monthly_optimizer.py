from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
import pandas as pd
import yfinance as yf


MARKET_PRESETS = {
    "US": ["SPY", "QQQ", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "AMD", "MU"],
    "INDIA": ["^NSEI", "^NSEBANK", "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS",
              "INFY.NS", "TCS.NS", "LT.NS", "BHARTIARTL.NS", "SUNPHARMA.NS"],
}


@dataclass(frozen=True)
class BacktestConfig:
    holding_days: int
    stop_loss: float
    take_profit: float


def market_universe(market: str, tickers: list[str] | None = None) -> list[str]:
    key = market.upper()
    if key not in MARKET_PRESETS:
        raise ValueError(f"unsupported market: {market}; use US or INDIA")
    selected = tickers or MARKET_PRESETS[key]
    return list(dict.fromkeys(x.strip().upper() for x in selected if x.strip()))[:50]


def _download(ticker: str, period: str = "5y") -> pd.DataFrame:
    history = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if history.empty:
        raise ValueError(f"no price history available for {ticker}")
    return history.dropna(subset=["Close"])


def _trade_return(prices: pd.Series, start: int, config: BacktestConfig) -> tuple[float, int, str]:
    entry = float(prices.iloc[start])
    end = min(len(prices) - 1, start + config.holding_days)
    for i in range(start + 1, end + 1):
        ret = float(prices.iloc[i] / entry - 1.0)
        if ret <= -config.stop_loss:
            return -config.stop_loss, i - start, "STOP"
        if ret >= config.take_profit:
            return config.take_profit, i - start, "TARGET"
    return float(prices.iloc[end] / entry - 1.0), end - start, "TIME"


def _momentum_signal(prices: pd.Series, i: int) -> bool:
    if i < 63:
        return False
    return (
        float(prices.iloc[i] / prices.iloc[i - 21] - 1.0) > 0
        and float(prices.iloc[i] / prices.iloc[i - 63] - 1.0) > 0
    )


def _evaluate_config(prices: pd.Series, config: BacktestConfig, start: int) -> dict[str, float]:
    returns: list[float] = []
    durations: list[int] = []
    for i in range(max(63, start), len(prices) - config.holding_days, config.holding_days):
        if not _momentum_signal(prices, i):
            continue
        ret, days, _ = _trade_return(prices, i, config)
        returns.append(ret)
        durations.append(days)
    if not returns:
        return {"compound": 0.0, "avg_return": 0.0, "hit_rate": 0.0, "trades": 0.0, "avg_days": 0.0}
    return {
        "compound": float(np.prod([1.0 + x for x in returns]) - 1.0),
        "avg_return": float(np.mean(returns)),
        "hit_rate": float(np.mean(np.array(returns) > 0)),
        "trades": float(len(returns)),
        "avg_days": float(np.mean(durations)),
    }


def optimize_monthly_plan(ticker: str, benchmark: str | None = "^GSPC", period: str = "5y") -> dict:
    history = _download(ticker, period)
    prices = history["Close"].astype(float)
    if len(prices) < 252:
        raise ValueError(f"insufficient history for {ticker}")

    # The newest 63 trading days are held out from parameter selection.
    test_start = max(63, len(prices) - 63)
    train = prices.iloc[:test_start]
    configs = [
        BacktestConfig(h, sl, tp)
        for h, sl, tp in product(
            (10, 15, 20, 30), (0.04, 0.06, 0.08, 0.10), (0.08, 0.12, 0.16, 0.20)
        )
    ]
    scored = [(cfg, _evaluate_config(train, cfg, 63)) for cfg in configs]
    viable = [(cfg, s) for cfg, s in scored if s["trades"] >= 5]
    cfg, train_score = max(
        viable or scored,
        key=lambda x: (x[1]["compound"], x[1]["hit_rate"], x[1]["avg_return"]),
    )

    out = _evaluate_config(prices, cfg, test_start)
    current = float(prices.iloc[-1])
    signal = _momentum_signal(prices, len(prices) - 1)
    action = "BUY" if signal and out["trades"] >= 2 and out["avg_return"] > 0 else "HOLD"

    benchmark_return = None
    excess = None
    if benchmark:
        try:
            b = _download(benchmark, period)["Close"].astype(float)
            aligned = pd.concat([prices, b], axis=1, join="inner").dropna()
            if len(aligned) >= 64:
                stock_ret = float(aligned.iloc[-1, 0] / aligned.iloc[-64, 0] - 1)
                benchmark_return = float(aligned.iloc[-1, 1] / aligned.iloc[-64, 1] - 1)
                excess = stock_ret - benchmark_return
        except Exception:
            pass

    confidence = min(
        0.95,
        0.45
        + 0.20 * min(1.0, out["trades"] / 10.0)
        + 0.20 * out["hit_rate"]
        + 0.15 * max(0.0, min(1.0, train_score["hit_rate"])),
    )
    expected = max(-cfg.stop_loss, min(cfg.take_profit, out["avg_return"]))
    return {
        "ticker": ticker.upper(),
        "current_price": current,
        "action": action,
        "config": asdict(cfg),
        "expected_return": expected,
        "benchmark_return": benchmark_return,
        "expected_excess_return": excess,
        "historical_hit_rate": out["hit_rate"],
        "historical_trades": int(out["trades"]),
        "confidence": confidence,
        "train_compound_return": train_score["compound"],
        "out_of_sample_compound_return": out["compound"],
        "target_price": current * (1.0 + cfg.take_profit),
        "stop_price": current * (1.0 - cfg.stop_loss),
        "rationale": [
            f"{cfg.holding_days}-trading-day time stop",
            f"{cfg.stop_loss:.0%} hard stop / {cfg.take_profit:.0%} target",
            f"{out['trades']:.0f} out-of-sample trades, {out['hit_rate']:.0%} hit rate",
            "21d and 63d momentum both positive" if signal else "momentum gate is not currently positive",
        ],
    }


def build_monthly_recommendations(
    market: str,
    tickers: list[str] | None = None,
    benchmark: str | None = None,
) -> dict:
    symbols = market_universe(market, tickers)
    benchmark = benchmark or ("^GSPC" if market.upper() == "US" else "^NSEI")
    plans, errors = [], []
    for ticker in symbols:
        try:
            plans.append(optimize_monthly_plan(ticker, benchmark=benchmark))
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})

    plans.sort(
        key=lambda x: (
            x["action"] == "BUY",
            x["expected_return"],
            x["confidence"],
            x["historical_hit_rate"],
        ),
        reverse=True,
    )
    for rank, plan in enumerate(plans, 1):
        plan["rank"] = rank
    return {
        "market": market.upper(),
        "benchmark": benchmark,
        "horizon_days": 30,
        "objective": "maximize expected one-month return subject to hard risk limits and out-of-sample validation",
        "plans": plans,
        "errors": errors,
    }
