from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import requests

from .macro_adapter import live_macro, fred_series
from .regime_intelligence import classify_market_regime


@dataclass(frozen=True)
class MacroState:
    as_of: str
    regime: dict
    fiscal_deficit: float | None
    debt_to_gdp: float | None
    policy_rate: float | None
    long_rate: float | None
    fx_usd_local: float | None
    dollar_index: float | None
    credit_stress: float | None
    growth_signal: float | None
    inflation_signal: float | None
    sources: tuple[str, ...]


def _fred_value(series_id: str) -> float | None:
    result = fred_series(series_id, limit=5)
    if result.get("status") != "ok":
        return None
    for row in result.get("observations", []):
        try:
            if row.get("value") not in (None, "."):
                return float(row["value"])
        except (TypeError, ValueError):
            continue
    return None


def macro_state(market: str = "US") -> dict:
    market = market.upper()
    base = live_macro()
    regime = classify_market_regime()

    # Defaults are intentionally explicit and overrideable. India fiscal/debt data is
    # maintained by official Ministry/RBI releases rather than silently substituted with US data.
    ids = {
        "US": {
            "fiscal_deficit": "FYFSD", "debt_to_gdp": "GFDEGDQ188S",
            "policy_rate": "DFF", "long_rate": "DGS10",
            "fx_usd_local": None, "dollar_index": "DTWEXBGS", "credit_stress": "BAMLH0A0HYM2",
            "growth_signal": "GDPC1", "inflation_signal": "CPIAUCSL",
        },
        "INDIA": {
            "fiscal_deficit": os.getenv("TRADINGDYOR_INDIA_FISCAL_FRED"),
            "debt_to_gdp": os.getenv("TRADINGDYOR_INDIA_DEBT_FRED"),
            "policy_rate": os.getenv("TRADINGDYOR_INDIA_POLICY_FRED"),
            "long_rate": os.getenv("TRADINGDYOR_INDIA_LONG_RATE_FRED"),
            "fx_usd_local": "DEXINUS", "dollar_index": None,
            "credit_stress": os.getenv("TRADINGDYOR_INDIA_CREDIT_FRED"),
            "growth_signal": os.getenv("TRADINGDYOR_INDIA_GROWTH_FRED"),
            "inflation_signal": os.getenv("TRADINGDYOR_INDIA_INFLATION_FRED"),
        },
    }.get(market, {})

    values = {k: (_fred_value(v) if v else None) for k, v in ids.items()}
    sources = list(base.get("sources", []))
    sources.extend(["FRED where configured", "RBI/Ministry of Finance official releases for India fiscal and debt data"])
    result = MacroState(
        as_of=datetime.now(timezone.utc).isoformat(),
        regime=asdict(regime),
        fiscal_deficit=values.get("fiscal_deficit"),
        debt_to_gdp=values.get("debt_to_gdp"),
        policy_rate=values.get("policy_rate"),
        long_rate=values.get("long_rate"),
        fx_usd_local=values.get("fx_usd_local"),
        dollar_index=values.get("dollar_index"),
        credit_stress=values.get("credit_stress"),
        growth_signal=values.get("growth_signal"),
        inflation_signal=values.get("inflation_signal"),
        sources=tuple(dict.fromkeys(sources)),
    )
    return asdict(result)


def macro_pressure(state: dict) -> float:
    regime = state.get("regime", {})
    pressure = float(regime.get("stress", 0.0) or 0.0)
    if state.get("credit_stress") is not None:
        pressure += min(0.25, max(0.0, float(state["credit_stress"]) / 10.0))
    if state.get("inflation_signal") is not None and state.get("policy_rate") is not None:
        pressure += min(0.20, max(0.0, (float(state["policy_rate"]) - 0.03)))
    return min(1.0, pressure)
