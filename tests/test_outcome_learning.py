from tradingdyor.outcome_learning import DecisionEpisode, OutcomeMemory, stable_episode_id


def test_episode_id_is_stable():
    assert stable_episode_id("MSFT", "2026-09-27T00:00:00+00:00") == stable_episode_id("msft", "2026-09-27T00:00:00+00:00")


def test_outcome_memory_round_trip(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="abc", ticker="MSFT", decision_at="2026-09-20T00:00:00+00:00",
        action="BUY", entry_price=100, thesis="earnings growth supports upside",
        score=.4, confidence=.8, horizon_days=7,
        strategy_scores={"quality_growth": .8, "momentum": .2},
        sources=("SEC", "Company IR"), capabilities=("fundamentals", "earnings"),
        verification_depth=1.5,
    )
    memory.record_decision(episode)
    loaded = OutcomeMemory(tmp_path / "outcomes.json")
    assert loaded.get("abc") == episode
    assert loaded.outcome_stats()["observations"] == 0.0


def test_pending_only_returns_due_episodes(tmp_path):
    memory = OutcomeMemory(tmp_path / "outcomes.json")
    episode = DecisionEpisode(
        id="future", ticker="MSFT", decision_at="2099-01-01T00:00:00+00:00",
        action="BUY", entry_price=100, thesis="x", score=.2, confidence=.7,
        horizon_days=7, strategy_scores={}, sources=(), capabilities=(), verification_depth=1.0,
    )
    memory.record_decision(episode)
    assert memory.pending() == []
