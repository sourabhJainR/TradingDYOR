from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from statistics import mean, pstdev
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
DEFAULT_TIMEOUT_SECONDS = 8.0
MIN_SENTIMENT_ARTICLES = 5
MIN_SENTIMENT_PUBLISHERS = 3

_EVENT_TERMS = {
    "earnings": ("earnings", "revenue", "profit", "guidance", "quarterly results"),
    "merger_acquisition": ("acquisition", "merger", "takeover", "buyout"),
    "legal_regulatory": ("lawsuit", "investigation", "regulator", "antitrust", "sec probe", "fine"),
    "product_contract": ("launch", "product", "contract", "order", "partnership", "customer"),
    "leadership": ("ceo", "cfo", "resigns", "appointed", "steps down"),
    "cybersecurity": ("cyberattack", "breach", "ransomware", "cybersecurity"),
    "capital_allocation": ("buyback", "dividend", "debt offering", "share sale"),
}


def _parse_seen_at(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for fmt in ("%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%SZ"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _parse_published_at(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _event_type(title: str) -> str:
    normalized = title.casefold()
    for event_type, terms in _EVENT_TERMS.items():
        if any(term in normalized for term in terms):
            return event_type
    return "general"


def _story_key(title: str, url: str) -> str:
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    identity = normalized_title or url.strip().casefold()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _sentiment(articles: list[dict[str, Any]]) -> dict[str, Any]:
    # Only GDELT tone is used. Google News RSS adds source diversity and publication
    # timestamps, but its headlines are not converted into a sentiment score.
    observations = [
        (article["tone"], article.get("publisher_domains") or [article.get("publisher", "")])
        for article in articles
        if article.get("tone") is not None
    ]
    publishers = {publisher for _, domains in observations for publisher in domains if publisher}
    if len(observations) < MIN_SENTIMENT_ARTICLES or len(publishers) < MIN_SENTIMENT_PUBLISHERS:
        return {
            "status": "unscored",
            "method": "GDELT article tone aggregate",
            "score": None,
            "sample_count": len(observations),
            "publisher_count": len(publishers),
            "dispersion": None,
            "confidence": 0.0,
            "reason": "insufficient independent articles or publisher diversity",
        }
    tones = [tone for tone, _ in observations]
    dispersion = pstdev(tones) if len(tones) > 1 else 0.0
    confidence = min(1.0, len(tones) / 15.0) * min(1.0, len(publishers) / 5.0)
    confidence *= max(0.0, 1.0 - min(1.0, dispersion / 40.0) * 0.5)
    return {
        "status": "scored",
        "method": "GDELT article tone aggregate; not analyst consensus",
        "score": round(mean(tones), 3),
        "sample_count": len(tones),
        "publisher_count": len(publishers),
        "dispersion": round(dispersion, 3),
        "confidence": round(confidence, 3),
        "reason": None,
    }


def _story(
    *,
    title: str,
    url: str,
    publisher: str,
    publisher_domain: str,
    provider: str,
    published_at: str | None = None,
    seen_at: str | None = None,
    tone: float | None = None,
) -> dict[str, Any] | None:
    title = title.strip()[:500]
    url = url.strip()
    if not title or not url.startswith(("https://", "http://")):
        return None
    domain = publisher_domain.strip().lower().removeprefix("www.") or _domain(url)
    return {
        "story_id": _story_key(title, url),
        "title": title,
        "url": url,
        "publisher": publisher.strip() or domain,
        "publisher_domains": [domain] if domain else [],
        "source_urls": [url],
        "source_providers": [provider],
        "publish_time": published_at,
        "seen_at": seen_at,
        "event_type": _event_type(title),
        "tone": tone,
        "duplicate_count": 1,
    }


def _merge_story(grouped: dict[str, dict[str, Any]], article: dict[str, Any]) -> None:
    current = grouped.get(article["story_id"])
    if current is None:
        grouped[article["story_id"]] = article
        return
    current["duplicate_count"] += 1
    for field in ("publisher_domains", "source_urls", "source_providers"):
        current[field] = sorted(set(current.get(field, [])) | set(article.get(field, [])))
    if not current.get("publish_time") and article.get("publish_time"):
        current["publish_time"] = article["publish_time"]
    if not current.get("seen_at") and article.get("seen_at"):
        current["seen_at"] = article["seen_at"]
    if current.get("tone") is None and article.get("tone") is not None:
        current["tone"] = article["tone"]
    current["publisher_count"] = len(current["publisher_domains"])


def _fetch_gdelt(
    query: str, timespan: str, limit: int, timeout: float, session: Any,
) -> dict[str, Any]:
    try:
        response = session.get(
            GDELT_DOC_API,
            params={
                "query": query, "mode": "ArtList", "format": "json",
                "sort": "HybridRel", "maxrecords": limit, "timespan": timespan,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        raw_articles = payload.get("articles", []) if isinstance(payload, dict) else []
        if not isinstance(raw_articles, list):
            raise ValueError("GDELT response articles field is not a list")
        articles = []
        for raw in raw_articles:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "")
            url = str(raw.get("url") or "")
            domain = str(raw.get("domain") or raw.get("sourceCommonName") or _domain(url))
            article = _story(
                title=title, url=url, publisher=domain, publisher_domain=domain,
                provider="GDELT", seen_at=_parse_seen_at(raw.get("seendate")),
                tone=_number(raw.get("tone")),
            )
            if article:
                articles.append(article)
        return {"status": "available" if articles else "empty", "articles": articles, "error": None}
    except Exception as exc:
        return {"status": "unavailable", "articles": [], "error": type(exc).__name__}


def _fetch_google_news(
    query: str, market: str, limit: int, timeout: float, session: Any,
) -> dict[str, Any]:
    locale = {"US": ("US", "US:en"), "INDIA": ("IN", "IN:en")}[market]
    try:
        response = session.get(
            GOOGLE_NEWS_RSS,
            params={
                "q": query, "hl": "en-US", "gl": locale[0], "ceid": locale[1],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        raw_content = getattr(response, "content", None)
        if raw_content is None:
            raw_text = getattr(response, "text", "")
            raw_content = raw_text.encode("utf-8") if isinstance(raw_text, str) else b""
        root = ET.fromstring(raw_content)
        articles = []
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title") or ""
            url = item.findtext("link") or ""
            source = item.find("source")
            publisher = (source.text or "").strip() if source is not None else ""
            source_url = source.attrib.get("url", "") if source is not None else ""
            article = _story(
                title=title, url=url, publisher=publisher,
                publisher_domain=_domain(source_url) or _domain(url),
                provider="Google News RSS",
                published_at=_parse_published_at(item.findtext("pubDate")),
            )
            if article:
                articles.append(article)
        return {"status": "available" if articles else "empty", "articles": articles, "error": None}
    except Exception as exc:
        return {"status": "unavailable", "articles": [], "error": type(exc).__name__}


def fetch_company_news(
    ticker: str,
    company_name: str | None = None,
    *,
    timespan: str = "7d",
    limit: int = 25,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    market: str = "US",
    session: Any = requests,
    rss_session: Any = requests,
    include_gdelt: bool = True,
    include_google_news: bool = True,
) -> dict[str, Any]:
    """Fetch bounded multi-source company news with partial results and source times."""
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", symbol):
        raise ValueError("ticker must be a valid uppercase market symbol")
    if timespan not in {"1d", "3d", "7d", "14d", "30d"}:
        raise ValueError("timespan must be one of 1d, 3d, 7d, 14d, 30d")
    if market not in {"US", "INDIA"}:
        raise ValueError("market must be US or INDIA")
    if type(include_gdelt) is not bool or type(include_google_news) is not bool:
        raise ValueError("provider selection flags must be booleans")
    if not include_gdelt and not include_google_news:
        raise ValueError("at least one news provider must be enabled")
    bounded_limit = max(1, min(int(limit), 50))
    bounded_timeout = max(0.5, min(float(timeout), 8.0))
    company = " ".join((company_name or "").split())[:100]
    query = f'"{company}" OR "{symbol}"' if company else f'"{symbol}"'
    retrieved_at = datetime.now(timezone.utc).isoformat()

    with ThreadPoolExecutor(max_workers=int(include_gdelt) + int(include_google_news)) as pool:
        futures = {}
        if include_gdelt:
            futures["GDELT"] = pool.submit(
                _fetch_gdelt, query, timespan, bounded_limit, bounded_timeout, session,
            )
        if include_google_news:
            futures["Google News RSS"] = pool.submit(
                _fetch_google_news, company or symbol, market, bounded_limit, bounded_timeout, rss_session,
            )
        provider_results = {name: future.result() for name, future in futures.items()}

    grouped: dict[str, dict[str, Any]] = {}
    for result in provider_results.values():
        for article in result["articles"]:
            _merge_story(grouped, article)
    articles = sorted(
        grouped.values(),
        key=lambda item: item.get("seen_at") or item.get("publish_time") or "",
        reverse=True,
    )[:bounded_limit]
    for article in articles:
        article["publisher_count"] = len(article["publisher_domains"])

    statuses = [result["status"] for result in provider_results.values()]
    failed_count = statuses.count("unavailable")
    if failed_count == len(statuses):
        status = "unavailable"
    elif failed_count:
        status = "partial"
    elif articles:
        status = "available"
    else:
        status = "empty"

    return {
        "status": status,
        "providers": [
            {"name": name, "status": result["status"], "error_type": result["error"]}
            for name, result in provider_results.items()
        ],
        "ticker": symbol,
        "market": market,
        "query": query,
        "retrieved_at": retrieved_at,
        "timespan": timespan,
        "article_count": len(articles),
        "articles": articles,
        "sentiment": _sentiment(articles),
        "advisory_only": True,
    }
