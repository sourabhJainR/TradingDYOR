from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
import json

import yfinance as yf


@dataclass(frozen=True)
class RegimeState:
    name: str
    score: float
    volatility: float | None
    drawdown: float | None
    trend: float | None
    stress: float
    confidence: float
    evidence: tuple[str, ...]


def _series(ticker: str, period: str = "15y"):
    try:
        return yf.Ticker(ticker).history(period=period, auto_adjust=True)["Close"].dropna()
    except Exception:
        return None


def classify_market_regime() -> RegimeState:
    close = _series("SPY", "15y")
    vix = _series("^VIX", "15y")
    if close is None or close.empty:
        return RegimeState("unknown", 0.0, None, None, None, 0.5, 0.2, ("market history unavailable",))

    daily = close.pct_change().dropna()
    vol = float(daily.tail(63).std() * sqrt(252)) if len(daily) >= 63 else None
    ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    trend = float(close.iloc[-1] / ma200 - 1.0) if ma200 else None
    peak = float(close.cummax().iloc[-1])
    drawdown = float(close.iloc[-1] / peak - 1.0) if peak else None
    vix_level = float(vix.iloc[-1] / 100.0) if vix is not None and len(vix) else None

    stress = 0.0
    evidence = []
    if vol is not None:
        stress += min(1.0, max(0.0, (vol - 0.15) / 0.35)) * 0.35
        evidence.append(f"annualized 63d volatility={vol:.1%}")
    if drawdown is not None:
        stress += min(1.0, max(0.0, -drawdown / 0.35)) * 0.40
        evidence.append(f"peak drawdown={drawdown:.1%}")
    if vix_level is not None:
        stress += min(1.0, max(0.0, (vix_level - 0.18) / 0.45)) * 0.25
        evidence.append(f"VIX={vix_level:.1%}")

    if stress >= 0.70:
        name = "crisis"
    elif stress >= 0.45:
        name = "high-stress"
    elif stress >= 0.25:
        name = "slowdown"
    elif trend is not None and trend > 0.05 and (vol is None or vol < 0.22):
        name = "expansion"
    else:
        name = "normal"

    score = max(-1.0, min(1.0, (trend or 0.0) - stress))
    confidence = min(0.98, 0.45 + 0.12 * len(evidence))
    return RegimeState(name, score, vol, drawdown, trend, min(1.0, stress), confidence, tuple(evidence))


def regime_multiplier(state: RegimeState, action: str) -> float:
    # Risk-aware, not return-blind: preserve upside in stressed markets while demanding a
    # larger signal when the environment has historically carried more adverse movement.
    if action == "BUY":
        return {"crisis": 0.72, "high-stress": 0.82, "slowdown": 0.90}.get(state.name, 1.0)
    if action == "SELL":
        return {"crisis": 1.08, "high-stress": 1.05, "slowdown": 1.02}.get(state.name, 1.0)
    return 1.0


@dataclass
class EventForecast:
    event_id: str
    category: str
    entity: str
    expected_at: str
    window_start: str
    window_end: str
    importance: float
    probability: float
    expected_direction: float
    source: str
    created_at: str
    observed_at: str | None = None
    timing_error_days: float | None = None
    market_reaction: float | None = None
    surprise: float | None = None


class EventMemory:
    def __init__(self, path: str | Path = ".tradingdyor/events.json", max_records: int = 10000):
        self.path = Path(path)
        self.max_records = max_records
        self.events: list[EventForecast] = []
        self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            self.events = [EventForecast(**x) for x in data.get("events", [])][-self.max_records:]
        except (OSError, ValueError, TypeError):
            self.events = []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"events": [asdict(x) for x in self.events[-self.max_records:]]}, indent=2))

    def record_forecast(self, event: EventForecast):
        self.events = [x for x in self.events if x.event_id != event.event_id]
        self.events.append(event)
        self.save()

    def record_observation(self, event_id: str, observed_at: str, reaction: float,
                           surprise: float | None = None):
        for event in reversed(self.events):
            if event.event_id == event_id:
                expected = datetime.fromisoformat(event.expected_at.replace("Z", "+00:00"))
                observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                event.observed_at = observed_at
                event.timing_error_days = (observed - expected).total_seconds() / 86400.0
                event.market_reaction = reaction
                event.surprise = surprise
                self.save()
                return event
        raise KeyError(event_id)

    def calibration(self):
        observed = [x for x in self.events if x.observed_at and x.market_reaction is not None]
        if not observed:
            return {"observations": 0}
        timing = [abs(x.timing_error_days or 0.0) for x in observed]
        directional = [
            (x.expected_direction == 0.0) or (x.expected_direction * x.market_reaction > 0)
            for x in observed
        ]
        return {
            "observations": len(observed),
            "event_direction_accuracy": sum(directional) / len(directional),
            "mean_timing_error_days": sum(timing) / len(timing),
            "mean_market_reaction": sum(x.market_reaction for x in observed) / len(observed),
        }


def extreme_event_history() -> list[dict]:
    # Stable anchors used to prevent optimistic models from treating every current regime
    # as unprecedented. The model also learns new episodes from observed market data.
    return [
        {"name": "global-financial-crisis", "period": "2007-10..2009-03", "class": "crisis"},
        {"name": "euro-area-stress", "period": "2011-07..2012-06", "class": "high-stress"},
        {"name": "covid-shock", "period": "2020-02..2020-04", "class": "crisis"},
        {"name": "inflation-rate-shock", "period": "2022-01..2022-10", "class": "high-stress"},
        {"name": "regional-bank-stress", "period": "2023-03..2023-05", "class": "high-stress"},
    ]
