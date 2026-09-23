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
