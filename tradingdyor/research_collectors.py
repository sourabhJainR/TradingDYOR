from __future__ import annotations

from .earnings import earnings_signal
from .filings import filing_signal_tags, sec_filings
from .market_data import snapshot_ticker
from .market_intelligence import corporate_actions_history, earnings_history, sec_insider_transactions
from .macro_intelligence import macro_state, macro_pressure
from .news_sentiment import fetch_company_news
from .regime_intelligence import EventMemory
from .event_intelligence import event_pressure
from dataclasses import asdict
import os
from .patents import search_patents
from .sector_adapter import sector_state


def _claims(source: str, pairs: list[tuple[str, object]]) -> list[dict]:
    return [{"claim": key, "value": str(value), "source": source} for key, value in pairs]


def fundamentals(ticker: str) -> dict:
    s = snapshot_ticker(ticker.upper())
    return {
        "evidence_count": 1,
        "snapshot": s.model_dump(mode="json"),
        "claims": _claims("Market data", [("price", s.price), ("revenue growth", s.revenue_growth), ("roe", s.roe)]),
    }


def filings(ticker: str) -> dict:
    rows = sec_filings(ticker.upper(), limit=20)
    return {
        "evidence_count": len(rows),
        "filings": [{"form": f.form, "filed": f.filed, "document": f.primary_document, "url": f.url} for f in rows],
        "claims": _claims("SEC", [("filing activity", len(rows))]),
        "tags": [tag for f in rows for tag in filing_signal_tags(f"{f.form} {f.primary_document}")],
    }


def insiders(ticker: str) -> dict:
    rows = sec_insider_transactions(ticker.upper(), limit=20)
    buys = sum(float(r.shares or 0) for r in rows if r.transaction_code == "P")
    sells = sum(float(r.shares or 0) for r in rows if r.transaction_code == "S")
    return {"evidence_count": len(rows), "buys": buys, "sells": sells, "claims": _claims("SEC", [("insider purchases", buys), ("insider sales", sells)])}


def earnings(ticker: str) -> dict:
    rows = earnings_history(ticker.upper(), limit=8)
    signal = earnings_signal(rows)
    return {"evidence_count": len(rows), "signal": signal, "claims": _claims("Market data", [("earnings observations", len(rows)), ("earnings signal", signal)])}


def corporate_actions(ticker: str) -> dict:
    rows = corporate_actions_history(ticker.upper())
    return {
        "evidence_count": len(rows),
        "actions": rows,
        "claims": _claims("Market data", [("corporate actions", len(rows))]),
    }


def sector(ticker: str) -> dict:
    # Sector lookup is intentionally separated from ticker identity resolution.
    s = snapshot_ticker(ticker.upper())
    sector_name = getattr(s, "sector", None) or "Unknown"
    result = sector_state(sector_name)
    return {"evidence_count": 1, "sector": sector_name, "result": result, "claims": _claims("Market data", [("sector", sector_name), ("sector score", result.get("score"))])}


def macro(ticker: str) -> dict:
    market = "INDIA" if ticker.upper().endswith((".NS", ".BO")) else "US"
    result = macro_state(market)
    return {
        "status": "available" if result.get("regime", {}).get("name") != "unknown" else "unavailable",
        "evidence_count": 1 if result.get("regime", {}).get("name") != "unknown" else 0,
        "macro": result,
        "macro_pressure": macro_pressure(result),
        "claims": _claims("Market data", [
            ("market regime", result.get("regime", {}).get("name")),
            ("macro pressure", macro_pressure(result)),
        ]),
    }


def news(ticker: str) -> dict:
    market = "INDIA" if ticker.upper().endswith((".NS", ".BO")) else "US"
    result = fetch_company_news(ticker.upper(), timespan="7d", market=market)
    articles = result.get("articles", []) if isinstance(result, dict) else []
    claims = []
    for article in articles if isinstance(articles, list) else []:
        if not isinstance(article, dict):
            continue
        claims.append({
            "claim": "news:" + str(article.get("story_id") or article.get("url") or ""),
            "value": str(article.get("title") or ""),
            "source": str(article.get("publisher") or "news"),
            "url": str(article.get("url") or ""),
            "available_at": article.get("publish_time"),
            "observed_at": article.get("seen_at"),
            "confidence": 0.4,
            "relevance": 0.5,
        })
    return {
        "status": result.get("status", "unavailable"),
        "evidence_count": len(articles),
        "news": result,
        "sentiment": result.get("sentiment", {"status": "unscored"}),
        "claims": claims,
    }


def events(ticker: str) -> dict:
    path = os.environ.get("TRADINGDYOR_EVENT_DB", ".tradingdyor/events.json")
    memory = EventMemory(path)
    symbol = ticker.strip().upper()
    selected = [
        event for event in memory.events
        if event.category != "company"
        or event.entity.strip().upper() in {
            symbol, symbol.removesuffix(".NS"), symbol.removesuffix(".BO"),
        }
    ]
    pressure = event_pressure(memory, symbol)
    return {
        "status": "unavailable" if memory.load_status == "unavailable" else "available" if selected else "empty",
        "error_type": memory.load_error_type,
        "evidence_count": len(selected),
        "event_pressure": pressure,
        "events": [asdict(event) for event in selected],
        "claims": _claims("Event memory", [
            ("tracked event count", len(selected)),
            ("upcoming event pressure", pressure),
        ]),
    }


def patents(ticker: str) -> dict:
    # Company-name resolution is optional; the collector remains explicit when the API key is absent.
    s = snapshot_ticker(ticker.upper())
    company = getattr(s, "company_name", None)
    result = search_patents(company, 10) if company else {"status": "unavailable", "patents": []}
    return {"evidence_count": len(result.get("patents", [])), "patents": result, "claims": _claims("USPTO/PatentsView", [("patent status", result.get("status"))])}


COLLECTORS = {
    "fundamentals": fundamentals,
    "filings": filings,
    "insiders": insiders,
    "earnings": earnings,
    "corporate_actions": corporate_actions,
    "sector": sector,
    "macro": macro,
    "news": news,
    "events": events,
    "patents": patents,
}
