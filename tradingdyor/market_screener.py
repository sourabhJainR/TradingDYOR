from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any

import yfinance as yf

CACHE_TTL_SECONDS = 300
STALE_TTL_SECONDS = 1800
MAX_PAGE_SIZE = 250
MAX_OFFSET = 10_000
VALID_MARKETS = {"US", "INDIA"}
VALID_SECTORS = {
    "Basic Materials", "Communication Services", "Consumer Cyclical",
    "Consumer Defensive", "Energy", "Financial Services", "Healthcare",
    "Industrials", "Real Estate", "Technology", "Utilities",
}

_CACHE: dict[tuple, dict[str, Any]] = {}
_CACHE_LOCK = RLock()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _quote_as_of(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _query(
    market: str,
    sector: str | None,
    max_pe: float | None,
    min_revenue_growth: float | None,
    min_market_cap: float | None,
    min_average_volume: float | None,
):
    filters = []
    if market == "US":
        filters.append(yf.EquityQuery("eq", ["region", "us"]))
    else:
        filters.extend([
            yf.EquityQuery("eq", ["region", "in"]),
            yf.EquityQuery("is-in", ["exchange", "NSI", "BSE"]),
        ])
    if sector:
        filters.append(yf.EquityQuery("eq", ["sector", sector]))
    if max_pe is not None:
        filters.append(yf.EquityQuery("lte", ["peratio.lasttwelvemonths", max_pe]))
    if min_revenue_growth is not None:
        # Yahoo's screener field uses percentage points; app inputs use decimals.
        filters.append(yf.EquityQuery(
            "gte", ["quarterlyrevenuegrowth.quarterly", min_revenue_growth * 100.0],
        ))
    if min_market_cap is not None:
        filters.append(yf.EquityQuery("gte", ["intradaymarketcap", min_market_cap]))
    if min_average_volume is not None:
        filters.append(yf.EquityQuery("gte", ["avgdailyvol3m", min_average_volume]))
    return yf.EquityQuery("and", filters)


def _normalize_quote(raw: dict[str, Any]) -> dict[str, Any] | None:
    ticker = raw.get("symbol") or raw.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        return None
    return {
        "ticker": ticker.strip().upper(),
        "name": raw.get("shortName") or raw.get("longName") or raw.get("displayName"),
        "exchange": raw.get("exchange") or raw.get("fullExchangeName"),
        "sector": raw.get("sector"),
        "price": _number(raw.get("regularMarketPrice", raw.get("intradayprice"))),
        "currency": raw.get("currency"),
        "market_cap": _number(raw.get("marketCap", raw.get("intradaymarketcap"))),
        "pe": _number(raw.get("trailingPE", raw.get("peratio.lasttwelvemonths"))),
        "revenue_growth": _number(raw.get("revenueGrowth", raw.get("quarterlyrevenuegrowth.quarterly"))),
        "average_volume_3m": _number(raw.get("averageDailyVolume3Month", raw.get("avgdailyvol3m"))),
        "as_of": _quote_as_of(raw.get("regularMarketTime")),
        "source": "Yahoo Finance via yfinance",
    }


def screen_market(
    *,
    market: str = "US",
    sector: str | None = None,
    max_pe: float | None = None,
    min_revenue_growth: float | None = None,
    min_market_cap: float | None = None,
    min_average_volume: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Bounded, cached US/India equity screening with explicit stale/unavailable states."""
    market = market.upper()
    if market not in VALID_MARKETS:
        raise ValueError("market must be US or INDIA")
    if sector is not None and sector not in VALID_SECTORS:
        raise ValueError("unsupported sector")
    if max_pe is not None and not 0 < float(max_pe) <= 200:
        raise ValueError("max_pe must be between 0 and 200")
    if min_revenue_growth is not None and not -1 <= float(min_revenue_growth) <= 5:
        raise ValueError("min_revenue_growth must be between -1 and 5")
    if min_market_cap is not None and not 0 <= float(min_market_cap) <= 10_000_000_000_000:
        raise ValueError("min_market_cap is outside the supported range")
    if min_average_volume is not None and not 0 <= float(min_average_volume) <= 1_000_000_000:
        raise ValueError("min_average_volume is outside the supported range")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise ValueError(f"offset must be between 0 and {MAX_OFFSET}")

    key = (
        market, sector, max_pe, min_revenue_growth, min_market_cap,
        min_average_volume, limit, offset,
    )
    now = datetime.now(timezone.utc)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and (now - cached["fetched_at"]).total_seconds() <= CACHE_TTL_SECONDS:
            return {**cached["payload"], "cache_status": "hit"}

    try:
        query = _query(market, sector, max_pe, min_revenue_growth, min_market_cap, min_average_volume)
        response = yf.screen(
            query,
            offset=offset,
            size=limit,
            sortField="intradaymarketcap",
            sortAsc=False,
        )
        raw_quotes = response.get("quotes", []) if isinstance(response, dict) else []
        if not isinstance(raw_quotes, list):
            raise ValueError("Yahoo screener returned an invalid quotes collection")
        items = [
            item for item in (_normalize_quote(raw) for raw in raw_quotes if isinstance(raw, dict))
            if item is not None
        ]
        total = int(response.get("total", len(items))) if isinstance(response, dict) else len(items)
        payload = {
            "status": "available" if items else "empty",
            "market": market,
            "items": items,
            "total": max(0, total),
            "offset": offset,
            "limit": limit,
            "next_offset": offset + len(items) if offset + len(items) < max(0, total) else None,
            "retrieved_at": now.isoformat(),
            "filters": {
                "sector": sector,
                "max_pe": max_pe,
                "min_revenue_growth": min_revenue_growth,
                "min_market_cap": min_market_cap,
                "min_average_volume": min_average_volume,
            },
            "provider": "Yahoo Finance via yfinance",
            "provider_status": "available",
            "cache_status": "miss",
            "error_type": None,
            "advisory_only": True,
        }
        with _CACHE_LOCK:
            _CACHE[key] = {"fetched_at": now, "payload": payload}
            if len(_CACHE) > 256:
                oldest = min(_CACHE, key=lambda item: _CACHE[item]["fetched_at"])
                _CACHE.pop(oldest, None)
        return payload
    except Exception as exc:
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
        if cached and (now - cached["fetched_at"]).total_seconds() <= STALE_TTL_SECONDS:
            return {
                **cached["payload"],
                "status": "stale",
                "provider_status": "unavailable",
                "cache_status": "stale_fallback",
                "error_type": type(exc).__name__,
            }
        return {
            "status": "unavailable",
            "market": market,
            "items": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "next_offset": None,
            "retrieved_at": now.isoformat(),
            "filters": {
                "sector": sector,
                "max_pe": max_pe,
                "min_revenue_growth": min_revenue_growth,
                "min_market_cap": min_market_cap,
                "min_average_volume": min_average_volume,
            },
            "provider": "Yahoo Finance via yfinance",
            "provider_status": "unavailable",
            "cache_status": "miss",
            "error_type": type(exc).__name__,
            "advisory_only": True,
        }


def clear_screener_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
