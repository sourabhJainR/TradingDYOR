from fastapi.testclient import TestClient
import pandas as pd

from tradingdyor.api import app
from tradingdyor.events import Event, filing_events, corporate_action_keywords
from tradingdyor.filings import Filing, filing_signal_tags
from tradingdyor.flows import normalize_flow_rows
from tradingdyor.macro import classify_regime
from tradingdyor.walk_forward import walk_forward_momentum, summarize_walk_forward


def test_filing_tags_and_events_are_deterministic():
    text = "The company announced guidance, an acquisition and a cybersecurity incident."
    assert filing_signal_tags(text) == ["guidance", "acquisition", "cyber"]
    filing = Filing("TEST", "8-K", "2026-01-02", "0001", "x.htm", "https://example.test/x")
    assert filing_events([filing]) == [Event("TEST", "2026-01-02", "8-K", "https://example.test/x")]


def test_flow_normalization_and_macro_regime():
    rows = normalize_flow_rows("NVDA", [{"filing_date": "2026-01-01",
          "holder": "Fund", "shares": "10", "value": "1000"}])
    assert rows[0].ticker == "NVDA"
    assert rows[0].shares == 10.0
    assert classify_regime(0.12, 0.15, 0.04).name == "risk-on"
    assert "dividend" in corporate_action_keywords()


def test_walk_forward_has_no_lookahead_and_summarizes():
    prices = pd.Series(
        [100, 102, 104, 106, 108, 110, 112, 114],
        index=pd.date_range("2025-01-01", periods=8, freq="MS"),
    )
    result = walk_forward_momentum(prices, train_months=3, test_months=2)
    assert not result.empty
    assert list(result.columns) == ["date", "signal", "forward_return"]
    summary = summarize_walk_forward(result)
    assert summary["observations"] == float(len(result))


def test_spa_is_served():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "TradingDYOR" in response.text


def test_news_sentiment_only_reduces_confidence_when_it_conflicts_with_fundamentals():
    from tradingdyor.decision import decide
    from tradingdyor.models import SecuritySnapshot

    snapshot = SecuritySnapshot(
        ticker="TEST",
        price=100.0,
        pe=15.0,
        ps=3.0,
        revenue_growth=0.6,
        earnings_growth=0.7,
        roe=0.3,
        debt_to_equity=0.3,
        momentum_12m=0.4,
        volatility_90d=0.2,
        evidence_coverage=0.9,
    )
    baseline = decide(snapshot)
    conflicting = decide(snapshot.model_copy(update={
        "news_sentiment_status": "scored",
        "news_sentiment_score": -4.0,
        "news_sentiment_confidence": 1.0,
        "news_sample_count": 12,
        "news_publisher_count": 5,
    }))
    assert conflicting.action == baseline.action
    assert conflicting.score == baseline.score
    assert conflicting.confidence < baseline.confidence
    assert any("news tone conflicts" in reason for reason in conflicting.key_reasons)


def test_thin_news_sample_does_not_change_fundamental_decision():
    from tradingdyor.decision import decide
    from tradingdyor.models import SecuritySnapshot

    snapshot = SecuritySnapshot(
        ticker="TEST",
        price=100.0,
        pe=15.0,
        ps=3.0,
        revenue_growth=0.6,
        earnings_growth=0.7,
        roe=0.3,
        debt_to_equity=0.3,
        momentum_12m=0.4,
        volatility_90d=0.2,
        evidence_coverage=0.9,
    )
    baseline = decide(snapshot)
    thin = decide(snapshot.model_copy(update={
        "news_sentiment_status": "unscored",
        "news_sample_count": 2,
        "news_publisher_count": 1,
    }))
    assert thin.action == baseline.action
    assert thin.score == baseline.score
    assert thin.confidence == baseline.confidence
    assert any("news sentiment unscored" in reason for reason in thin.key_reasons)


def test_snapshot_separates_market_observation_time_from_retrieval_time(monkeypatch):
    import pandas as pd
    from tradingdyor.market_data import snapshot_ticker

    index = pd.date_range("2026-02-13", periods=260, freq="D", tz="UTC")
    close = pd.Series([100.0 + index_value for index_value in range(260)], index=index)

    class FakeTicker:
        info = {
            "currency": "INR", "marketCap": 10_000_000,
            "averageVolume": 100_000, "dividendYield": 0.01,
            "trailingPE": float("nan"), "longName": "Example Limited",
        }

        def history(self, **_kwargs):
            return pd.DataFrame({"Close": close})

    monkeypatch.setattr("tradingdyor.market_data.yf.Ticker", lambda _ticker: FakeTicker())
    snapshot = snapshot_ticker("EXAMPLE.NS")
    assert snapshot.price_as_of == index[-1].to_pydatetime()
    assert snapshot.retrieved_at >= snapshot.price_as_of
    assert snapshot.as_of == snapshot.retrieved_at
    assert snapshot.currency == "INR"
    assert snapshot.pe is None
    assert snapshot.average_volume == 100_000
    assert snapshot.dividend_yield == 0.01


def test_news_collector_preserves_partial_provider_status_and_source_times(monkeypatch):
    from tradingdyor import research_collectors

    seen = {}
    def fake_news(ticker, **kwargs):
        seen["ticker"] = ticker
        seen.update(kwargs)
        return {
            "status": "partial", "article_count": 1,
            "retrieved_at": "2026-10-31T00:00:00+00:00",
            "articles": [{
                "story_id": "story-1", "title": "Issuer event",
                "publisher": "Publisher", "url": "https://publisher.example/story",
                "publish_time": "2026-10-30T12:00:00+00:00",
                "seen_at": "2026-10-30T12:01:00+00:00",
            }],
            "sentiment": {"status": "unscored", "sample_count": 1, "publisher_count": 1},
        }

    monkeypatch.setattr(research_collectors, "fetch_company_news", fake_news)
    result = research_collectors.news("RELIANCE.NS")
    assert seen["market"] == "INDIA"
    assert result["status"] == "partial"
    assert result["evidence_count"] == 1
    assert result["claims"][0]["available_at"] == "2026-10-30T12:00:00+00:00"
    assert result["claims"][0]["observed_at"] == "2026-10-30T12:01:00+00:00"


def test_macro_collector_uses_ticker_market(monkeypatch):
    from tradingdyor import research_collectors

    seen = []
    monkeypatch.setattr(research_collectors, "macro_state", lambda market: seen.append(market) or {
        "regime": {"name": "normal", "score": 0.2, "stress": 0.1},
    })
    monkeypatch.setattr(research_collectors, "macro_pressure", lambda _state: 0.15)
    result = research_collectors.macro("RELIANCE.NS")
    assert seen == ["INDIA"]
    assert result["macro_pressure"] == 0.15
    assert result["status"] == "available"


def test_unavailable_macro_context_does_not_emit_zero_pressure_claim(monkeypatch):
    from tradingdyor import research_collectors

    monkeypatch.setattr(research_collectors, "macro_state", lambda _market: {
        "regime": {"name": "unknown"},
    })
    monkeypatch.setattr(research_collectors, "macro_pressure", lambda _state: 0.0)
    result = research_collectors.macro("ABC")
    assert result["status"] == "unavailable"
    assert result["macro_pressure"] is None
    assert result["claims"] == []


def test_empty_or_corrupt_event_memory_is_not_reported_as_zero_event_risk(monkeypatch, tmp_path):
    from tradingdyor import research_collectors

    empty_path = tmp_path / "empty-events.json"
    monkeypatch.setenv("TRADINGDYOR_EVENT_DB", str(empty_path))
    empty = research_collectors.events("ABC")
    assert empty["status"] == "empty"
    assert empty["event_pressure"] is None
    assert all("upcoming event pressure" not in item["claim"] for item in empty["claims"])

    corrupt_path = tmp_path / "corrupt-events.json"
    corrupt_path.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("TRADINGDYOR_EVENT_DB", str(corrupt_path))
    corrupt = research_collectors.events("ABC")
    assert corrupt["status"] == "unavailable"
    assert corrupt["event_pressure"] is None
    assert corrupt["claims"] == []
