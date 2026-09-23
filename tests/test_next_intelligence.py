import pandas as pd

from tradingdyor.experience import Experience, ExperienceMemory
from tradingdyor.historical_financials import normalize_companyfacts
from tradingdyor.strategy_validation import walk_forward_strategies, summarize_strategy_walk_forward


def test_companyfacts_are_point_in_time_sorted():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"val": 100, "end": "2025-12-31", "filed": "2026-02-01", "form": "10-K", "accn": "a"},
        {"val": 90, "end": "2024-12-31", "filed": "2025-02-01", "form": "10-K", "accn": "b"},
    ]}}}}}
    rows = normalize_companyfacts("test", facts, ["Revenues"])
    assert [x.filed for x in rows] == ["2025-02-01", "2026-02-01"]
    assert rows[0].ticker == "TEST"


def test_strategy_walk_forward_and_experience_memory(tmp_path):
    prices = pd.Series(
        range(100, 180),
        index=pd.date_range("2019-01-01", periods=80, freq="MS"),
        dtype=float,
    )
    result = walk_forward_strategies(prices)
    assert not result.empty
    summary = summarize_strategy_walk_forward(result)
    assert summary["observations"] == float(len(result))

    memory = ExperienceMemory(tmp_path / "experience.json")
    memory.record(Experience("sec", True, 100, .8, 1.0, 0, .4))
    memory.record(Experience("browser", False, 900, .2, 1.5, 1, 0.0))
    assert memory.recommend(["sec", "browser"]) == "sec"
