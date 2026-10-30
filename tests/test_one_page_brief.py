from fastapi.testclient import TestClient

from tradingdyor.api import app


def test_one_page_brief_combines_company_recommendation_news_and_provenance(monkeypatch):
    monkeypatch.setattr("tradingdyor.api.research_ticker", lambda ticker: {
        "snapshot": {
            "ticker": ticker, "company_name": "Example Corp", "sector": "Technology",
            "price": 123.45, "market_cap": 1000000, "as_of": "2026-10-30T12:00:00+00:00",
        },
        "decision": {
            "ticker": ticker, "action": "HOLD", "score": 0.1, "confidence": 0.4,
            "evidence_coverage": 0.35, "strategy_agreement": 0.5,
            "thesis": "Insufficient evidence for a BUY.",
            "key_reasons": ["Coverage below threshold"], "risks": ["Stale news"],
            "invalidation": ["Reassess after next filing"],
        },
        "market_intelligence": {
            "filing_activity": {"count": 1, "recent": []},
            "earnings": {"observations": []}, "insiders": {"observations": []},
            "corporate_actions": {"count": 0}, "evidence_coverage": 0.25,
        },
    })
    monkeypatch.setattr("tradingdyor.api.fetch_company_news", lambda *args, **kwargs: {
        "status": "available", "retrieved_at": "2026-10-30T12:05:00+00:00",
        "articles": [{"title": "Example Corp update", "url": "https://news.example/story"}],
        "sentiment": {"status": "unscored", "sample_count": 1, "publisher_count": 1},
    })

    response = TestClient(app).get("/research/brief/EXAMPLE")
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["name"] == "Example Corp"
    assert data["recommendation"]["action"] == "HOLD"
    assert data["news"]["sentiment"]["status"] == "unscored"
    assert data["evidence"]["sources"][-1]["name"] == "GDELT news"
    assert data["advisory_only"] is True


def test_one_page_brief_ui_is_served():
    response = TestClient(app).get("/brief/NVDA")
    assert response.status_code == 200
    assert "One-page evidence-first stock brief" in response.text
    assert "News sentiment" in response.text


def test_one_page_brief_rejects_invalid_ticker_before_provider_calls(monkeypatch):
    def unexpected(_ticker):
        raise AssertionError("provider must not be called for invalid ticker")

    monkeypatch.setattr("tradingdyor.api.research_ticker", unexpected)
    response = TestClient(app).get("/research/brief/ACME%2FPRIVATE")
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid ticker symbol"
