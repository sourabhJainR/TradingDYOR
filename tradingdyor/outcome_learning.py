from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
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
            self.episodes = [self._episode_from_dict(x) for x in data.get("episodes", [])][-self.max_records:]
            self.outcomes = [Outcome(**x) for x in data.get("outcomes", [])][-self.max_records:]
        except (OSError, ValueError, TypeError):
            self.episodes, self.outcomes = [], []

    @staticmethod
    def _episode_from_dict(data: dict) -> DecisionEpisode:
        normalized = dict(data)
        normalized["sources"] = tuple(normalized.get("sources", ()))
        normalized["capabilities"] = tuple(normalized.get("capabilities", ()))
        normalized["strategy_scores"] = {
            str(k): float(v) for k, v in normalized.get("strategy_scores", {}).items()
        }
        return DecisionEpisode(**normalized)

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
        for episode in self.episodes:
            try:
                due = datetime.fromisoformat(episode.decision_at.replace("Z", "+00:00")) + timedelta(
                    days=episode.horizon_days
                )
                if episode.id not in done and now >= due:
                    result.append(episode)
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
            "avg_excess_return": (
                sum(x.excess_return for x in xs if x.excess_return is not None)
                / len([x for x in xs if x.excess_return is not None])
                if any(x.excess_return is not None for x in xs)
                else 0.0
            ),
        }

    def calibration_stats(self) -> dict[str, dict[str, dict[str, float]]]:
        """Return sample-aware outcome quality by strategy, source and capability.

        These are observational calibration signals, not causal attribution.
        """
        result: dict[str, dict[str, dict[str, float]]] = {}
        episodes = {x.id: x for x in self.episodes}
        for dimension in ("strategies", "sources", "capabilities"):
            buckets: dict[str, list[Outcome]] = {}
            for outcome in self.outcomes:
                episode = episodes.get(outcome.episode_id)
                if not episode:
                    continue
                names = (
                    episode.strategy_scores.keys()
                    if dimension == "strategies"
                    else getattr(episode, dimension)
                )
                for name in names:
                    buckets.setdefault(str(name), []).append(outcome)

            result[dimension] = {}
            for name, observations in buckets.items():
                hits = [x.directional_hit for x in observations if x.directional_hit is not None]
                excess = [x.excess_return for x in observations if x.excess_return is not None]
                hit_rate = sum(hits) / len(hits) if hits else 0.0
                # Bayesian-style shrinkage toward a neutral 50% prior avoids
                # overreacting to one or two outcomes.
                n = len(hits)
                shrunk_hit_rate = (sum(hits) + 2.0 * 0.5) / (n + 2.0) if n else 0.5
                result[dimension][name] = {
                    "observations": float(len(observations)),
                    "directional_hit_rate": hit_rate,
                    "shrunk_hit_rate": shrunk_hit_rate,
                    "avg_return": sum(x.realized_return for x in observations) / len(observations),
                    "avg_excess_return": sum(excess) / len(excess) if excess else 0.0,
                    "avg_max_adverse_return": sum(
                        x.max_adverse_return for x in observations
                    ) / len(observations),
                    "risk_rate": sum(x.risk_breached for x in observations) / len(observations),
                    "confidence": min(0.95, 0.5 + 0.05 * math.sqrt(len(observations))),
                }
        return result


def _safe_return(entry: float, price: float) -> float:
    return price / entry - 1.0 if entry else 0.0


def _target_index(index, target_at: datetime) -> int:
    """Find the first trading observation on/after the calendar target."""
    target_date = target_at.date()
    for position, timestamp in enumerate(index):
        if timestamp.date() >= target_date:
            return position
    return len(index) - 1


def evaluate_episode(episode: DecisionEpisode, benchmark: str | None = "^GSPC") -> Outcome:
    decision_at = datetime.fromisoformat(episode.decision_at.replace("Z", "+00:00"))
    target_at = decision_at + timedelta(days=episode.horizon_days)
    start = decision_at.date().isoformat()
    calendar_days = max(episode.horizon_days + 15, 30)
    history = yf.Ticker(episode.ticker).history(
        start=start, period=f"{calendar_days}d", auto_adjust=True
    )
    if history.empty:
        raise ValueError(f"no market history available for {episode.ticker}")

    close = history["Close"].dropna()
    if close.empty:
        raise ValueError(f"no closing prices available for {episode.ticker}")
    target_index = _target_index(close.index, target_at)
    returns = [_safe_return(episode.entry_price, float(x)) for x in close.iloc[: target_index + 1]]
    realized = returns[-1]

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
            bh = yf.Ticker(benchmark).history(
                start=start, period=f"{calendar_days}d", auto_adjust=True
            )["Close"].dropna()
            if not bh.empty:
                benchmark_target = _target_index(bh.index, target_at)
                benchmark_return = float(bh.iloc[benchmark_target] / bh.iloc[0] - 1.0)
        except Exception:
            benchmark_return = None
    excess = realized - benchmark_return if benchmark_return is not None else None

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
        episode_id=episode.id,
        ticker=episode.ticker,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        horizon_days=episode.horizon_days,
        realized_return=realized,
        max_favorable_return=max_favorable,
        max_adverse_return=max_adverse,
        benchmark_return=benchmark_return,
        excess_return=excess,
        directional_hit=directional_hit,
        thesis_hit=thesis_hit,
        risk_breached=risk_breached,
        attribution=attribution,
        recalibration=recalibration,
    )


def stable_episode_id(ticker: str, decision_at: str) -> str:
    import hashlib
    return hashlib.sha256(f"{ticker.upper()}|{decision_at}".encode()).hexdigest()[:20]
