import pandas as pd
import pytest

from tradingdyor.learning import RoutingPolicy
from tradingdyor.outcome_learning import (
    DecisionEpisode,
    OutcomeMemory,
    evaluate_episode,
    stable_episode_id,
)


def test_episode_id_is_stable():
    assert stable_episode_id("MSFT", "2026-09-27T00:00:00+00:00") == stable_episode_id(
        "msft", "2026-09-27T00:00:00+00:00"
    )


def test_outcome_memory_round_trip(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="abc",
        ticker="MSFT",
        decision_at="2026-09-20T00:00:00+00:00",
        action="BUY",
        entry_price=100,
        thesis="earnings growth supports upside",
        score=0.4,
        confidence=0.8,
        horizon_days=7,
        strategy_scores={"quality_growth": 0.8, "momentum": 0.2},
        sources=("SEC", "Company IR"),
        capabilities=("fundamentals", "earnings"),
        verification_depth=1.5,
    )
    memory.record_decision(episode)
    loaded = OutcomeMemory(tmp_path / "outcomes.json")
    assert loaded.get("abc") == episode
    assert loaded.outcome_stats()["observations"] == 0.0


def test_pending_only_returns_due_episodes(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="future",
        ticker="MSFT",
        decision_at="2099-01-01T00:00:00+00:00",
        action="BUY",
        entry_price=100,
        thesis="x",
        score=0.2,
        confidence=0.7,
        horizon_days=7,
        strategy_scores={},
        sources=(),
        capabilities=(),
        verification_depth=1.0,
    )
    memory.record_decision(episode)
    assert memory.pending() == []


def test_evaluate_episode_uses_calendar_horizon(monkeypatch):
    index = pd.to_datetime(
        ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-07", "2026-09-08"]
    )

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **kwargs):
            if self.ticker == "MSFT":
                return pd.DataFrame({"Close": [100, 101, 102, 110, 111]}, index=index)
            return pd.DataFrame({"Close": [100, 100, 101, 102, 103]}, index=index)

    monkeypatch.setattr("tradingdyor.outcome_learning.yf.Ticker", FakeTicker)
    episode = DecisionEpisode(
        id="calendar",
        ticker="MSFT",
        decision_at="2026-09-01T00:00:00+00:00",
        action="BUY",
        entry_price=100,
        thesis="upside",
        score=0.5,
        confidence=0.8,
        horizon_days=5,
        strategy_scores={"momentum": 0.7},
        sources=("SEC",),
        capabilities=("fundamentals",),
        verification_depth=1.0,
    )
    outcome = evaluate_episode(episode, benchmark="SPY")
    # Five calendar days after Sep 1 is Sep 6; Sep 7 is the first trading day on/after it.
    assert outcome.realized_return == pytest.approx(0.10)
    assert outcome.benchmark_return == pytest.approx(0.02)
    assert outcome.excess_return == pytest.approx(0.08)


def test_calibration_is_sample_aware(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="calibration",
        ticker="MSFT",
        decision_at="2026-09-01T00:00:00+00:00",
        action="BUY",
        entry_price=100,
        thesis="upside",
        score=0.5,
        confidence=0.8,
        horizon_days=7,
        strategy_scores={"momentum": 0.8},
        sources=("SEC",),
        capabilities=("fundamentals",),
        verification_depth=1.0,
    )
    memory.record_decision(episode)
    from tradingdyor.outcome_learning import Outcome

    memory.record_outcome(
        Outcome(
            episode_id="calibration",
            ticker="MSFT",
            evaluated_at="2026-09-10T00:00:00+00:00",
            horizon_days=7,
            realized_return=0.10,
            max_favorable_return=0.12,
            max_adverse_return=-0.02,
            benchmark_return=0.02,
            excess_return=0.08,
            directional_hit=True,
            thesis_hit=True,
            risk_breached=False,
            attribution={
                "strategies": {"momentum": 0.8},
                "sources": {"SEC": 1.0},
                "capabilities": {"fundamentals": 1.0},
                "verification": {"depth": 1.0, "outcome_signal": 1.0},
            },
            recalibration={},
        )
    )
    stats = memory.calibration_stats()
    assert stats["strategies"]["momentum"]["observations"] == 1.0
    assert stats["strategies"]["momentum"]["shrunk_hit_rate"] == 2 / 3
    assert stats["sources"]["SEC"]["avg_excess_return"] == 0.08


def test_policy_persistence_and_observation_decay(tmp_path):
    path = tmp_path / "policy.json"
    policy = RoutingPolicy()
    policy.update("fundamentals", True, 0.0, 0.2)
    policy.save(path)
    loaded = RoutingPolicy.load(path)
    assert loaded.capability_observations["fundamentals"] == 1
    first = loaded.capability_weight["fundamentals"]
    loaded.update("fundamentals", True, 0.0, 0.2)
    assert loaded.capability_weight["fundamentals"] > first
    assert loaded.capability_observations["fundamentals"] == 2


def test_calibration_exposes_horizon_quality(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="horizon",
        ticker="MSFT",
        decision_at="2026-09-01T00:00:00+00:00",
        action="BUY",
        entry_price=100,
        thesis="upside",
        score=0.5,
        confidence=0.8,
        horizon_days=30,
        strategy_scores={"momentum": 0.8},
        sources=("SEC",),
        capabilities=("fundamentals",),
        verification_depth=1.0,
    )
    memory.record_decision(episode)
    from tradingdyor.outcome_learning import Outcome

    memory.record_outcome(
        Outcome(
            episode_id="horizon",
            ticker="MSFT",
            evaluated_at="2026-10-01T00:00:00+00:00",
            horizon_days=30,
            realized_return=0.10,
            max_favorable_return=0.12,
            max_adverse_return=-0.04,
            benchmark_return=0.03,
            excess_return=0.07,
            directional_hit=True,
            thesis_hit=True,
            risk_breached=False,
            attribution={
                "strategies": {"momentum": 0.8},
                "sources": {"SEC": 1.0},
                "capabilities": {"fundamentals": 1.0},
                "verification": {"depth": 1.0, "outcome_signal": 1.0},
            },
            recalibration={},
        )
    )
    metrics = memory.calibration_stats()["horizons"]["30d"]
    assert metrics["observations"] == 1.0
    assert metrics["quality_signal"] == pytest.approx(0.07)
