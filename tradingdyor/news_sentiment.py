from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import re
from statistics import mean, pstdev
from typing import Any

import requests

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
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


def _sentiment(articles: list[dict[str, Any]]) -> dict[str, Any]:
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


def fetch_company_news(
    ticker: str,
    company_name: str | None = None,
    *,
    timespan: str = "7d",
    limit: int = 25,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    session: Any = requests,
) -> dict[str, Any]:
    """Fetch recent GDELT news; preserve partial/unavailable states and source timestamps."""
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", symbol):
        raise ValueError("ticker must be a valid uppercase market symbol")
    if timespan not in {"1d", "3d", "7d", "14d", "30d"}:
        raise ValueError("timespan must be one of 1d, 3d, 7d, 14d, 30d")
    bounded_limit = max(1, min(int(limit), 50))
    company = " ".join((company_name or "").split())[:100]
    query = f'"{company}" OR "{symbol}"' if company else f'"{symbol}"'

    retrieved_at = datetime.now(timezone.utc).isoformat()
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "maxrecords": bounded_limit,
        "timespan": timespan,
    }
    try:
        response = session.get(GDELT_DOC_API, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        raw_articles = payload.get("articles", []) if isinstance(payload, dict) else []
        if not isinstance(raw_articles, list):
            raise ValueError("GDELT response articles field is not a list")
    except Exception as exc:
        return {
            "status": "unavailable",
            "provider": "GDELT",
            "ticker": symbol,
            "query": query,
            "retrieved_at": retrieved_at,
            "timespan": timespan,
            "articles": [],
            "sentiment": _sentiment([]),
            "error": f"{type(exc).__name__}: news provider unavailable",
        }

    grouped: dict[str, dict[str, Any]] = {}
    for raw in raw_articles:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()[:500]
        url = str(raw.get("url") or "").strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        publisher = str(raw.get("domain") or raw.get("sourceCommonName") or "").strip().lower()
        if not publisher:
            publisher = re.sub(r"^www\.", "", url.split("/")[2].lower())
        key = _story_key(title, url)
        tone = _number(raw.get("tone"))
        article = grouped.get(key)
        if article is None:
            article = {
                "story_id": key,
                "title": title,
                "url": url,
                "publisher": publisher,
                "publish_time": None,
                "seen_at": _parse_seen_at(raw.get("seendate")),
                "event_type": _event_type(title),
                "tone": tone,
                "duplicate_count": 1,
                "publishers": [publisher],
                "source_urls": [url],
            }
            grouped[key] = article
        else:
            article["duplicate_count"] += 1
            if publisher not in article["publishers"]:
                article["publishers"].append(publisher)
            if url not in article["source_urls"]:
                article["source_urls"].append(url)
            existing_tone = article.get("tone")
            if existing_tone is None and tone is not None:
                article["tone"] = tone

    articles = sorted(
        grouped.values(),
        key=lambda item: item.get("seen_at") or "",
        reverse=True,
    )[:bounded_limit]
    for article in articles:
        article["publisher_domains"] = sorted(article["publishers"])
        article["publisher_count"] = len(article["publisher_domains"])
        article.pop("publishers", None)

    return {
        "status": "available" if articles else "empty",
        "provider": "GDELT",
        "ticker": symbol,
        "query": query,
        "retrieved_at": retrieved_at,
        "timespan": timespan,
        "article_count": len(articles),
        "articles": articles,
        "sentiment": _sentiment(articles),
        "error": None,
    }
