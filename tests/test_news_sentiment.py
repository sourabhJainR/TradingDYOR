from __future__ import annotations

from tradingdyor.news_sentiment import fetch_company_news


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        if self.error:
            raise self.error
        return _Response(self.payload)


def test_news_preserves_source_times_and_deduplicates_syndicated_titles():
    session = _Session({
        "articles": [
            {"title": "Acme announces quarterly earnings", "url": "https://a.example/story",
             "domain": "a.example", "seendate": "20261030T120000Z", "tone": 2.5},
            {"title": "Acme announces quarterly earnings", "url": "https://b.example/story",
             "domain": "b.example", "seendate": "20261030T121000Z", "tone": 3.0},
            {"title": "Acme faces antitrust investigation", "url": "https://c.example/story",
             "domain": "c.example", "seendate": "20261030T130000Z", "tone": -4.0},
        ]
    })
    result = fetch_company_news("ACME", "Acme Corp", session=session)

    assert result["status"] == "available"
    assert result["article_count"] == 2
    syndicated = next(x for x in result["articles"] if "earnings" in x["title"])
    assert syndicated["duplicate_count"] == 2
    assert syndicated["publisher_count"] == 2
    assert syndicated["seen_at"] == "2026-10-30T12:00:00+00:00"
    assert syndicated["publish_time"] is None
    assert syndicated["event_type"] == "earnings"
    assert result["sentiment"]["status"] == "unscored"
    assert session.calls[0][2] <= 8.0
    assert session.calls[0][1]["timespan"] == "7d"


def test_sentiment_requires_independent_sample_and_publisher_coverage():
    articles = [
        {"tone": float(i), "publisher": f"publisher-{i % 3}"}
        for i in range(6)
    ]
    session = _Session({"articles": [
        {"title": f"Acme update {i}", "url": f"https://p{i % 3}.example/{i}",
         "domain": f"p{i % 3}.example", "seendate": "20261030T120000Z",
         "tone": float(i - 3)}
        for i in range(6)
    ]})
    result = fetch_company_news("ACME", session=session)
    assert result["sentiment"]["status"] == "scored"
    assert result["sentiment"]["sample_count"] == 6
    assert result["sentiment"]["publisher_count"] == 3
    assert -3.0 <= result["sentiment"]["score"] <= 3.0
    assert 0.0 < result["sentiment"]["confidence"] <= 1.0


def test_news_provider_failure_is_explicit_partial_result():
    result = fetch_company_news("ACME", session=_Session(error=TimeoutError("private detail")))

    assert result["status"] == "unavailable"
    assert result["articles"] == []
    assert result["sentiment"]["status"] == "unscored"
    assert "TimeoutError" in result["error"]
    assert "private detail" not in result["error"]


def test_news_rejects_bad_ticker_and_timespan():
    import pytest

    with pytest.raises(ValueError):
        fetch_company_news("ACME/SECRET")
    with pytest.raises(ValueError):
        fetch_company_news("ACME", timespan="90d")
