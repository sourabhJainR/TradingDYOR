from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from tradingdyor.universe import UniverseProvider, screen_universe


def test_us_universe_parser_excludes_test_issues_and_etfs():
    nasdaq = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAA|Alpha Corp - Common Stock|Q|N|N|100|N|N
ETF1|Example ETF|Q|N|N|100|Y|N
TEST1|Test Corp|Q|Y|N|100|N|N
File Creation Time: 20261031
"""
    other = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BBB|Beta Inc - Common Stock|N|BBB|N|100|N|BBB
FUND|Fund Trust|N|FUND|Y|100|N|FUND
"""
    rows = UniverseProvider._parse_us(nasdaq, other)
    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert rows[1]["exchange"] == "NYSE"


def test_india_universe_parser_keeps_only_equity_series():
    text = """SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING
ABC,ABC Limited,EQ,2020-01-01
ABCBE,ABC SME,BE,2020-01-01
"""
    rows = UniverseProvider._parse_india(text)
    assert rows == [{"ticker": "ABC.NS", "name": "ABC Limited", "exchange": "NSE"}]


def test_stale_universe_cache_is_used_when_exchange_provider_fails(tmp_path):
    path = tmp_path / "us-universe-v1.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "US",
        "fetched_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "source_urls": ["https://exchange.example/list"],
        "symbols": [{"ticker": "AAA", "name": "Alpha", "exchange": "NASDAQ"}],
    }))

    class FailedSession:
        def get(self, *_args, **_kwargs):
            raise TimeoutError("private provider detail")

    result = UniverseProvider(tmp_path, session=FailedSession()).load("US", refresh=True)
    assert result["status"] == "stale"
    assert result["cache_status"] == "stale_fallback"
    assert result["symbols"][0]["ticker"] == "AAA"
    assert result["error_type"] == "TimeoutError"


def test_screener_applies_filters_and_reports_missing_metrics():
    class FakeUniverse:
        def load(self, market):
            return {
                "status": "available", "cache_status": "fresh",
                "fetched_at": "2026-10-31T00:00:00+00:00",
                "source_urls": ["https://exchange.example/list"],
                "symbols": [
                    {"ticker": "AAA", "name": "Alpha", "exchange": "NASDAQ"},
                    {"ticker": "BBB", "name": "Beta", "exchange": "NYSE"},
                ],
            }

    snapshots = {
        "AAA": {"ticker": "AAA", "market_cap": 5_000_000, "pe": 18.0, "revenue_growth": 0.2,
                "roe": 0.15, "currency": "USD", "price_as_of": "2026-10-30T20:00:00+00:00"},
        "BBB": {"ticker": "BBB", "market_cap": 2_000_000, "pe": None, "revenue_growth": 0.1,
                "roe": 0.12, "currency": "USD", "price_as_of": "2026-10-30T20:00:00+00:00"},
    }
    result = screen_universe(
        "US", offset=0, limit=2,
        filters={"min_market_cap": 1_000_000, "max_pe": 20},
        universe_provider=FakeUniverse(),
        snapshot_provider=lambda ticker: snapshots[ticker],
    )
    assert result["status"] == "available"
    assert [item["ticker"] for item in result["included"]] == ["AAA"]
    assert result["excluded"][0]["ticker"] == "BBB"
    assert "missing:pe" in result["excluded"][0]["exclusion_reasons"]
    assert result["next_offset"] == 2


def test_screener_uses_one_shared_deadline_for_universe_and_snapshots():
    import time

    class SlowUniverse:
        def load(self, market):
            time.sleep(0.7)
            return {
                "status": "available", "cache_status": "fresh",
                "fetched_at": None, "source_urls": [],
                "symbols": [{"ticker": "AAA", "name": "Alpha", "exchange": "NASDAQ"}],
            }

    called = []
    result = screen_universe(
        "US", timeout_seconds=0.5,
        universe_provider=SlowUniverse(),
        snapshot_provider=lambda ticker: called.append(ticker) or {"ticker": ticker},
    )
    assert result["status"] == "partial"
    assert result["timed_out"] == 1
    assert called == []


def test_exchange_download_stops_at_byte_limit_and_closes_response(monkeypatch, tmp_path):
    import pytest
    from tradingdyor import universe

    class Response:
        closed = False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield b"12345678"
            yield b"abcdefgh"

        def close(self):
            self.closed = True

    response = Response()
    class Session:
        def get(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(universe, "MAX_UNIVERSE_BYTES", 10)
    provider = UniverseProvider(tmp_path, session=Session())
    with pytest.raises(ValueError, match="byte limit"):
        provider._download("https://exchange.example/list")
    assert response.closed is True
