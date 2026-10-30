from datetime import datetime, timedelta, timezone

import pytest

from tradingdyor import market_screener
from tradingdyor.market_screener import clear_screener_cache, screen_market


class FakeQuery:
    def __init__(self, operator, operand):
        self.operator = operator
        self.operand = operand


@pytest.fixture(autouse=True)
def reset_cache():
    clear_screener_cache()
    yield
    clear_screener_cache()


def test_us_screener_builds_bounded_query_and_normalizes_quotes(monkeypatch):
    calls = []

    def fake_screen(query, **kwargs):
        calls.append((query, kwargs))
        return {
            "total": 260,
            "quotes": [{
                "symbol": "NVDA",
                "shortName": "NVIDIA Corporation",
                "exchange": "NMS",
                "sector": "Technology",
                "regularMarketPrice": 190.5,
                "currency": "USD",
                "marketCap": 4_000_000_000_000,
                "trailingPE": 45.2,
                "revenueGrowth": 0.18,
                "averageDailyVolume3Month": 30_000_000,
                "regularMarketTime": 1793448000,
            }],
        }

    monkeypatch.setattr(market_screener.yf, "EquityQuery", FakeQuery)
    monkeypatch.setattr(market_screener.yf, "screen", fake_screen)

    result = screen_market(
        market="US", sector="Technology", max_pe=50,
        min_revenue_growth=0.15, min_market_cap=1_000_000_000,
        min_average_volume=100_000, limit=100, offset=100,
    )

    query, kwargs = calls[0]
    assert query.operator == "and"
    assert ("eq", ["region", "us"]) in [(x.operator, x.operand) for x in query.operand]
    assert ("eq", ["sector", "Technology"]) in [(x.operator, x.operand) for x in query.operand]
    assert ("lte", ["peratio.lasttwelvemonths", 50.0]) in [(x.operator, x.operand) for x in query.operand]
    assert ("gte", ["quarterlyrevenuegrowth.quarterly", 15.0]) in [(x.operator, x.operand) for x in query.operand]
    assert kwargs == {"offset": 100, "size": 100, "sortField": "intradaymarketcap", "sortAsc": False}
    assert result["status"] == "available"
    assert result["total"] == 260
    assert result["next_offset"] == 101
    assert result["items"][0]["ticker"] == "NVDA"
    assert result["items"][0]["revenue_growth"] == 0.18
    assert result["items"][0]["currency"] == "USD"


def test_india_screener_limits_exchange_to_nse_and_bse(monkeypatch):
    captured = {}

    def fake_screen(query, **kwargs):
        captured["query"] = query
        return {"total": 0, "quotes": []}

    monkeypatch.setattr(market_screener.yf, "EquityQuery", FakeQuery)
    monkeypatch.setattr(market_screener.yf, "screen", fake_screen)
    result = screen_market(market="INDIA", limit=50)

    filters = [(x.operator, x.operand) for x in captured["query"].operand]
    assert ("eq", ["region", "in"]) in filters
    assert ("is-in", ["exchange", "NSI", "BSE"]) in filters
    assert result["status"] == "empty"


def test_screener_cache_and_explicit_stale_fallback(monkeypatch):
    calls = []

    def fake_screen(_query, **_kwargs):
        calls.append(True)
        return {"total": 1, "quotes": [{"symbol": "AAPL", "regularMarketPrice": 200}]}

    monkeypatch.setattr(market_screener.yf, "EquityQuery", FakeQuery)
    monkeypatch.setattr(market_screener.yf, "screen", fake_screen)
    first = screen_market(market="US", limit=10)
    second = screen_market(market="US", limit=10)
    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert len(calls) == 1

    key = ("US", None, None, None, None, None, 10, 0)
    market_screener._CACHE[key]["fetched_at"] = datetime.now(timezone.utc) - timedelta(minutes=10)
    monkeypatch.setattr(market_screener.yf, "screen", lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()))
    stale = screen_market(market="US", limit=10)
    assert stale["status"] == "stale"
    assert stale["provider_status"] == "unavailable"
    assert stale["cache_status"] == "stale_fallback"
    assert stale["items"][0]["ticker"] == "AAPL"


def test_screener_provider_failure_without_cache_is_unavailable(monkeypatch):
    monkeypatch.setattr(market_screener.yf, "EquityQuery", FakeQuery)
    monkeypatch.setattr(market_screener.yf, "screen", lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()))
    result = screen_market(market="US")
    assert result["status"] == "unavailable"
    assert result["provider_status"] == "unavailable"
    assert result["items"] == []
    assert result["error_type"] == "TimeoutError"


@pytest.mark.parametrize("kwargs", [
    {"market": "EU"},
    {"limit": 251},
    {"offset": -1},
    {"sector": "not-a-sector"},
    {"max_pe": 0},
    {"min_revenue_growth": 6},
])
def test_screener_rejects_invalid_filters(kwargs):
    with pytest.raises(ValueError):
        screen_market(**kwargs)
