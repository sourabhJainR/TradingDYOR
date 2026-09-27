from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import math

import yfinance as yf


@dataclass(frozen=True)
class DecisionEpisode:
    id: str
    ticker: str
    decision_at: str
    action: str
    entry_price: float
    thesis: str
    score: float
    confidence: float
    horizon_days: int
    strategy_scores: dict[str, float]
    sources: tuple[str, ...]
    capabilities: tuple[str, ...]
    verification_depth: float


@dataclass(frozen=True)
class Outcome:
    episode_id: str
    ticker: str
    evaluated_at: str
    horizon_days: int
    realized_return: float
    max_favorable_return: float
    max_adverse_return: float
    benchmark_return: float | None
    excess_return: float | None
    directional_hit: bool | None
    thesis_hit: bool | None
    risk_breached: bool
    attribution: dict[str, dict[str, float]]
    recalibration: dict[str, float]


class OutcomeMemory:
    def __init__(self, path: str | Path = ".tradingdyor/outcomes.json", max_records: int = 5000):
        self.path = Path(path)
        self.max_records = max(100, max_records)
        self.episodes: list[DecisionEpisode] = []
        self.outcomes: list[Outcome] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            self.episodes = [DecisionEpisode(**x) for x in data.get("episodes", [])][-self.max_records:]
            self.outcomes = [Outcome(**x) for x in data.get("outcomes", [])][-self.max_records:]
        except (OSError, ValueError, TypeError):
            self.episodes, self.outcomes = [], []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "episodes": [asdict(x) for x in self.episodes[-self.max_records:]],
            "outcomes": [asdict(x) for x in self.outcomes[-self.max_records:]],
        }, indent=2))

    def record_decision(self, episode: DecisionEpisode) -> None:
        if episode.horizon_days < 1 or episode.entry_price <= 0:
            raise ValueError("horizon_days must be positive and entry_price must be > 0")
        self.episodes = [x for x in self.episodes if x.id != episode.id]
        self.episodes.append(episode)
        self._save()

    def get(self, episode_id: str) -> DecisionEpisode | None:
        return next((x for x in self.episodes if x.id == episode_id), None)

    def record_outcome(self, outcome: Outcome) -> None:
        self.outcomes = [x for x in self.outcomes if x.episode_id != outcome.episode_id]
        self.outcomes.append(outcome)
        self._save()

    def pending(self, now: datetime | None = None) -> list[DecisionEpisode]:
        now = now or datetime.now(timezone.utc)
        done = {x.episode_id for x in self.outcomes}
        result = []
        for e in self.episodes:
            try:
                due = datetime.fromisoformat(e.decision_at.replace("Z", "+00:00")).timestamp() + e.horizon_days * 86400
                if e.id not in done and now.timestamp() >= due:
                    result.append(e)
            except ValueError:
                continue
        return result

    def outcome_stats(self) -> dict[str, float]:
        xs = self.outcomes
        if not xs:
            return {"observations": 0.0}
        returns = [x.realized_return for x in xs]
        hits = [x.directional_hit for x in xs if x.directional_hit is not None]
        return {
            "observations": float(len(xs)),
            "avg_realized_return": sum(returns) / len(returns),
            "win_rate": sum(r > 0 for r in returns) / len(returns),
            "directional_accuracy": sum(hits) / len(hits) if hits else 0.0,
            "avg_max_adverse_return": sum(x.max_adverse_return for x in xs) / len(xs),
        }


def _safe_return(entry: float, price: float) -> float:
    return price / entry - 1.0 if entry else 0.0


def evaluate_episode(episode: DecisionEpisode, benchmark: str | None = "^GSPC") -> Outcome:
    end = datetime.fromisoformat(episode.decision_at.replace("Z", "+00:00"))
    start = end.date().isoformat()
    history = yf.Ticker(episode.ticker).history(
        start=start, period=f"{max(episode.horizon_days + 10, 30)}d", auto_adjust=True
    )
    if history.empty:
        raise ValueError(f"no market history available for {episode.ticker}")

    close = history["Close"].dropna()
    if close.empty:
        raise ValueError(f"no closing prices available for {episode.ticker}")
    entry = float(episode.entry_price)
    returns = [_safe_return(entry, float(x)) for x in close]
    target_index = min(len(returns) - 1, episode.horizon_days)
    realized = returns[target_index]

    action = episode.action.upper()
    directional_hit = None if action == "HOLD" else (
        realized > 0 if action == "BUY" else realized < 0
    )
    thesis_hit = directional_hit
    max_favorable = max(returns) if action != "SELL" else -min(returns)
    max_adverse = min(returns) if action != "SELL" else -max(returns)
    risk_breached = max_adverse <= -0.15

    benchmark_return = None
    if benchmark:
        try:
            bh = yf.Ticker(benchmark).history(start=start, period=f"{max(episode.horizon_days + 10, 30)}d", auto_adjust=True)["Close"].dropna()
            if len(bh) > 1:
                benchmark_return = float(bh.iloc[target_index] / bh.iloc[0] - 1.0) if target_index < len(bh) else float(bh.iloc[-1] / bh.iloc[0] - 1.0)
        except Exception:
            benchmark_return = None
    excess = realized - benchmark_return if benchmark_return is not None else None

    # Attribution is intentionally directional and bounded: it says what was
    # aligned with the realized outcome, not that a single source caused it.
    direction = 1.0 if realized > 0 else -1.0 if realized < 0 else 0.0
    attribution = {
        "strategies": {
            name: float(max(-1.0, min(1.0, direction * score)))
            for name, score in episode.strategy_scores.items()
        },
        "sources": {name: float(direction) for name in episode.sources},
        "capabilities": {name: float(direction) for name in episode.capabilities},
        "verification": {
            "depth": float(episode.verification_depth),
            "outcome_signal": float(direction),
        },
    }
    recalibration = {
        "direction_error": 0.0 if directional_hit else 1.0 if directional_hit is False else 0.0,
        "return_signal": float(max(-1.0, min(1.0, realized))),
        "risk_penalty": 1.0 if risk_breached else 0.0,
    }
    return Outcome(
        episode_id=episode.id, ticker=episode.ticker,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        horizon_days=episode.horizon_days, realized_return=realized,
        max_favorable_return=max_favorable, max_adverse_return=max_adverse,
        benchmark_return=benchmark_return, excess_return=excess,
        directional_hit=directional_hit, thesis_hit=thesis_hit,
        risk_breached=risk_breached, attribution=attribution,
        recalibration=recalibration,
    )


def stable_episode_id(ticker: str, decision_at: str) -> str:
    import hashlib
    return hashlib.sha256(f"{ticker.upper()}|{decision_at}".encode()).hexdigest()[:20]
