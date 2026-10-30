from fastapi.testclient import TestClient

from tradingdyor.api import app
from types import SimpleNamespace


def test_one_page_brief_combines_company_recommendation_news_and_provenance(monkeypatch):
    graph = {"nodes": {
        "fundamentals": {"status": "completed", "evidence_count": 3, "result": {
            "snapshot": {
                "ticker": "EXAMPLE", "company_name": "Example Corp", "sector": "Technology",
                "price": 123.45, "market_cap": 1000000, "as_of": "2026-10-30T12:00:00+00:00",
            },
        }},
        "filings": {"status": "failed", "evidence_count": 0, "result": None},
        "insiders": {"status": "completed", "evidence_count": 0, "result": {"buys": 0, "sells": 0}},
        "earnings": {"status": "completed", "evidence_count": 0, "result": {"signal": {}}},
        "corporate_actions": {"status": "completed", "evidence_count": 0, "result": {"actions": []}},
    }}
    decision = {
        "ticker": "EXAMPLE", "action": "HOLD", "score": 0.1, "confidence": 0.4,
        "evidence_coverage": 0.35, "strategy_agreement": 0.5,
        "thesis": "Insufficient evidence for a BUY.",
        "key_reasons": ["Coverage below threshold"], "risks": ["Stale news"],
        "invalidation": ["Reassess after next filing"], "research_status": "partial",
        "missing_research_tasks": [{"task_id": "filings", "status": "failed"}],
    }
    run = SimpleNamespace(graph=graph, decision=decision, evidence_yield=0.5,
                          duration_ms=120.0, contradictions=[])
    monkeypatch.setattr("tradingdyor.api.ResearchOrchestrator",
                        lambda _fabric: SimpleNamespace(run=lambda _ticker, _collectors: run))
    monkeypatch.setattr("tradingdyor.api.fetch_company_news", lambda *args, **kwargs: {
        "status": "available", "retrieved_at": "2026-10-30T12:05:00+00:00",
        "providers": [{"name": "GDELT", "status": "empty"}, {"name": "Google News RSS", "status": "available"}],
        "articles": [{"title": "Example Corp update", "url": "https://news.example/story"}],
        "sentiment": {"status": "unscored", "sample_count": 1, "publisher_count": 1},
    })

    response = TestClient(app).get("/research/brief/EXAMPLE")
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["name"] == "Example Corp"
    assert data["recommendation"]["action"] == "HOLD"
    assert data["news"]["sentiment"]["status"] == "unscored"
    assert data["evidence"]["sources"][-1]["name"] == "Google News RSS"
    assert data["research"]["status"] == "partial"
    assert next(x for x in data["evidence"]["sources"] if x["name"] == "Regulatory filings")["status"] == "failed"
    assert data["advisory_only"] is True


def test_one_page_brief_ui_is_served():
    response = TestClient(app).get("/brief/NVDA")
    assert response.status_code == 200
    assert "One-page evidence-first stock brief" in response.text
    assert "News sentiment" in response.text


def test_one_page_brief_rejects_invalid_ticker_before_provider_calls(monkeypatch):
    def unexpected(_ticker):
        raise AssertionError("provider must not be called for invalid ticker")

    monkeypatch.setattr("tradingdyor.api.ResearchOrchestrator", unexpected)
    response = TestClient(app).get("/research/brief/ACME%21")
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid ticker symbol"


def test_one_page_brief_abstains_when_graph_has_no_fundamental_snapshot(monkeypatch):
    run = SimpleNamespace(
        graph={"nodes": {"fundamentals": {"status": "failed", "result": None, "evidence_count": 0}}},
        decision={"status": "unavailable"},
        evidence_yield=0.0,
        duration_ms=10.0,
        contradictions=[],
    )
    monkeypatch.setattr("tradingdyor.api.ResearchOrchestrator",
                        lambda _fabric: SimpleNamespace(run=lambda _ticker, _collectors: run))
    monkeypatch.setattr("tradingdyor.api.fetch_company_news", lambda *args, **kwargs: {
        "status": "unavailable", "retrieved_at": "2026-10-30T12:05:00+00:00",
        "articles": [], "sentiment": {"status": "unscored", "sample_count": 0,
                                      "publisher_count": 0},
    })

    data = TestClient(app).get("/research/brief/EXAMPLE").json()
    assert data["recommendation"]["action"] == "HOLD"
    assert data["recommendation"]["research_status"] == "unavailable"
    assert data["company"]["price"] is None


def test_news_api_selects_india_sources_for_indian_ticker(monkeypatch):
    seen = {}
    def fake_news(ticker, **kwargs):
        seen["ticker"] = ticker
        seen.update(kwargs)
        return {"status": "empty", "providers": []}

    monkeypatch.setattr("tradingdyor.api.fetch_company_news", fake_news)
    response = TestClient(app).get("/research/news/RELIANCE.NS")
    assert response.status_code == 200
    assert seen["market"] == "INDIA"
    assert seen["ticker"] == "RELIANCE.NS"
