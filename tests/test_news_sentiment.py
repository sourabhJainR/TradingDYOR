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
    result = fetch_company_news("ACME", "Acme Corp", session=session, include_google_news=False)

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
    result = fetch_company_news("ACME", session=session, include_google_news=False)
    assert result["sentiment"]["status"] == "scored"
    assert result["sentiment"]["sample_count"] == 6
    assert result["sentiment"]["publisher_count"] == 3
    assert -3.0 <= result["sentiment"]["score"] <= 3.0
    assert 0.0 < result["sentiment"]["confidence"] <= 1.0


def test_news_provider_failure_is_explicit_partial_result():
    result = fetch_company_news("ACME", session=_Session(error=TimeoutError("private detail")), include_google_news=False)

    assert result["status"] == "unavailable"
    assert result["articles"] == []
    assert result["sentiment"]["status"] == "unscored"
    assert result["providers"][0]["error_type"] == "TimeoutError"
    assert "private detail" not in str(result)


def test_news_rejects_bad_ticker_and_timespan():
    import pytest

    with pytest.raises(ValueError):
        fetch_company_news("ACME/SECRET", include_google_news=False)
    with pytest.raises(ValueError):
        fetch_company_news("ACME", timespan="90d", include_google_news=False)


class _RssResponse:
    def __init__(self, xml):
        self.content = xml.encode("utf-8")

    def raise_for_status(self):
        return None


class _RssSession:
    def __init__(self, xml=None, error=None):
        self.xml = xml or "<rss><channel /></rss>"
        self.error = error
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        if self.error:
            raise self.error
        return _RssResponse(self.xml)


def test_google_news_rss_preserves_publication_time_and_india_market():
    rss = _RssSession("""<rss><channel><item>
      <title>Reliance announces quarterly earnings</title>
      <link>https://news.google.com/rss/articles/example</link>
      <pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate>
      <source url="https://www.publisher.example/">Publisher One</source>
    </item></channel></rss>""")
    result = fetch_company_news(
        "RELIANCE.NS", market="INDIA", include_gdelt=False, rss_session=rss,
    )

    assert result["status"] == "available"
    article = result["articles"][0]
    assert article["publish_time"] == "2026-10-30T12:00:00+00:00"
    assert article["seen_at"] is None
    assert article["publisher_domains"] == ["publisher.example"]
    assert result["sentiment"]["status"] == "unscored"
    assert rss.calls[0][1]["gl"] == "IN"
    assert rss.calls[0][1]["ceid"] == "IN:en"
    assert rss.calls[0][2] <= 8.0


def test_gdelt_failure_keeps_google_news_partial_result():
    rss = _RssSession("""<rss><channel><item>
      <title>Acme wins major contract</title>
      <link>https://news.google.com/rss/articles/contract</link>
      <pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate>
      <source url="https://publisher.example/">Publisher</source>
    </item></channel></rss>""")
    result = fetch_company_news(
        "ACME", session=_Session(error=TimeoutError("private detail")),
        rss_session=rss,
    )

    assert result["status"] == "partial"
    assert result["article_count"] == 1
    assert result["sentiment"]["status"] == "unscored"
    assert {x["name"]: x["status"] for x in result["providers"]} == {
        "GDELT": "unavailable", "Google News RSS": "available",
    }


def test_cross_source_story_dedup_preserves_both_publishers_and_providers():
    gdelt = _Session({"articles": [{
        "title": "Acme announces quarterly earnings",
        "url": "https://a.example/story",
        "domain": "a.example",
        "seendate": "20261030T120000Z",
        "tone": 2.5,
    }]})
    rss = _RssSession("""<rss><channel><item>
      <title>Acme announces quarterly earnings</title>
      <link>https://news.google.com/rss/articles/earnings</link>
      <pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate>
      <source url="https://b.example/">Publisher B</source>
    </item></channel></rss>""")
    result = fetch_company_news("ACME", session=gdelt, rss_session=rss)

    assert result["article_count"] == 1
    article = result["articles"][0]
    assert article["duplicate_count"] == 2
    assert article["publisher_count"] == 2
    assert article["source_providers"] == ["GDELT", "Google News RSS"]
    assert article["tone"] == 2.5
    assert article["publish_time"] == "2026-10-30T12:00:00+00:00"
    assert result["sentiment"]["sample_count"] == 1
    assert result["sentiment"]["status"] == "unscored"


def test_both_news_sources_unavailable_is_not_a_success():
    result = fetch_company_news(
        "ACME",
        session=_Session(error=TimeoutError("private")),
        rss_session=_RssSession(error=TimeoutError("private")),
    )
    assert result["status"] == "unavailable"
    assert result["articles"] == []
    assert all(x["status"] == "unavailable" for x in result["providers"])
