from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from io import StringIO
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Mapping

import requests

from .market_data import snapshot_ticker

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MAX_UNIVERSE_BYTES = 10_000_000
MAX_UNIVERSE_SYMBOLS = 50_000
UNIVERSE_TTL_SECONDS = 24 * 60 * 60
SNAPSHOT_TTL_SECONDS = 15 * 60
MAX_SCREENER_PAGE_SIZE = 12
MAX_SNAPSHOT_IN_FLIGHT = 16
_SNAPSHOT_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tradingdyor-screener")
_SNAPSHOT_SLOTS = threading.BoundedSemaphore(MAX_SNAPSHOT_IN_FLIGHT)
_SNAPSHOT_LOCK = threading.RLock()
_SNAPSHOT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_EXCHANGE_CODES = {"N": "NYSE", "A": "NYSE_AMERICAN", "P": "NYSE_ARCA", "Z": "CBOE", "V": "IEX"}


class UniverseUnavailable(RuntimeError):
    pass


class UniverseProvider:
    """Cached official exchange symbol directories with bounded payloads."""

    def __init__(
        self,
        cache_dir: str | Path = ".tradingdyor/universes",
        *,
        session: Any = requests,
        timeout: float = 8.0,
        ttl_seconds: int = UNIVERSE_TTL_SECONDS,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.session = session
        self.timeout = max(0.5, min(float(timeout), 8.0))
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, market: str) -> Path:
        return self.cache_dir / (market.lower() + "-universe-v1.json")

    def _download(self, url: str) -> str:
        response = self.session.get(
            url,
            timeout=self.timeout,
            headers={"User-Agent": "TradingDYOR/0.1 research-contact"},
        )
        response.raise_for_status()
        payload = getattr(response, "content", b"")
        if not isinstance(payload, (bytes, bytearray)) or len(payload) > MAX_UNIVERSE_BYTES:
            raise ValueError("exchange universe response exceeded the configured byte limit")
        return bytes(payload).decode("utf-8-sig", errors="replace")

    @staticmethod
    def _parse_us(nasdaq_text: str, other_text: str) -> list[dict[str, str]]:
        symbols: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(StringIO(nasdaq_text), delimiter="|"):
            ticker = (row.get("Symbol") or "").strip().upper()
            if not ticker or ticker.startswith("File Creation Time") or row.get("Test Issue") == "Y":
                continue
            if row.get("ETF") == "Y" or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,9}", ticker):
                continue
            symbols[ticker] = {
                "ticker": ticker,
                "name": (row.get("Security Name") or ticker).strip(),
                "exchange": "NASDAQ",
            }
        for row in csv.DictReader(StringIO(other_text), delimiter="|"):
            ticker = (row.get("ACT Symbol") or "").strip().upper()
            if not ticker or ticker.startswith("File Creation Time") or row.get("Test Issue") == "Y":
                continue
            if row.get("ETF") == "Y" or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,9}", ticker):
                continue
            exchange = _EXCHANGE_CODES.get((row.get("Exchange") or "").strip(), "OTHER_US")
            symbols.setdefault(ticker, {
                "ticker": ticker,
                "name": (row.get("Security Name") or ticker).strip(),
                "exchange": exchange,
            })
        return sorted(symbols.values(), key=lambda row: row["ticker"])[:MAX_UNIVERSE_SYMBOLS]

    @staticmethod
    def _parse_india(text: str) -> list[dict[str, str]]:
        rows = []
        for row in csv.DictReader(StringIO(text)):
            ticker = (row.get("SYMBOL") or "").strip().upper()
            series = (row.get("SERIES") or "").strip().upper()
            if series != "EQ" or not re.fullmatch(r"[A-Z0-9&\-]{1,20}", ticker):
                continue
            rows.append({
                "ticker": ticker + ".NS",
                "name": (row.get("NAME OF COMPANY") or ticker).strip(),
                "exchange": "NSE",
            })
        unique = {row["ticker"]: row for row in rows}
        return sorted(unique.values(), key=lambda row: row["ticker"])[:MAX_UNIVERSE_SYMBOLS]

    def load(self, market: str, *, refresh: bool = False) -> dict[str, Any]:
        market = market.strip().upper()
        if market not in {"US", "INDIA"}:
            raise ValueError("market must be US or INDIA")
        path = self._cache_path(market)
        cached = None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            age = (datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc)).total_seconds()
            if not refresh and age <= self.ttl_seconds:
                return {
                    "status": "available", "cache_status": "fresh",
                    "fetched_at": cached["fetched_at"], "source_urls": cached["source_urls"],
                    "symbols": cached["symbols"],
                }
        except (OSError, ValueError, KeyError, TypeError):
            cached = None

        try:
            if market == "US":
                nasdaq = self._download(NASDAQ_LISTED_URL)
                other = self._download(OTHER_LISTED_URL)
                symbols = self._parse_us(nasdaq, other)
                urls = [NASDAQ_LISTED_URL, OTHER_LISTED_URL]
            else:
                symbols = self._parse_india(self._download(NSE_EQUITY_URL))
                urls = [NSE_EQUITY_URL]
            if not symbols:
                raise ValueError("exchange universe response contained no eligible equity symbols")
            fetched_at = datetime.now(timezone.utc).isoformat()
            payload = {
                "schema_version": 1, "market": market, "fetched_at": fetched_at,
                "source_urls": urls, "symbols": symbols,
            }
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temp.replace(path)
            return {"status": "available", "cache_status": "refreshed", **payload}
        except Exception as exc:
            if isinstance(cached, dict) and isinstance(cached.get("symbols"), list) and cached["symbols"]:
                return {
                    "status": "stale", "cache_status": "stale_fallback",
                    "fetched_at": cached.get("fetched_at"), "source_urls": cached.get("source_urls", []),
                    "symbols": cached["symbols"], "error_type": type(exc).__name__,
                }
            return {
                "status": "unavailable", "cache_status": "miss",
                "fetched_at": None, "source_urls": [],
                "symbols": [], "error_type": type(exc).__name__,
            }


def _cached_snapshot(ticker: str) -> dict[str, Any]:
    now = time.monotonic()
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(ticker)
        if cached and cached[0] > now:
            return cached[1]
    snapshot = snapshot_ticker(ticker)
    payload = snapshot.model_dump(mode="json")
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE[ticker] = (now + SNAPSHOT_TTL_SECONDS, payload)
    return payload


def _filter_reasons(snapshot: Mapping[str, Any], filters: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    missing: list[str] = []
    checks = (
        ("min_market_cap", "market_cap", lambda value, limit: value >= limit),
        ("max_pe", "pe", lambda value, limit: 0 < value <= limit),
        ("min_revenue_growth", "revenue_growth", lambda value, limit: value >= limit),
        ("min_earnings_growth", "earnings_growth", lambda value, limit: value >= limit),
        ("min_roe", "roe", lambda value, limit: value >= limit),
        ("max_debt_to_equity", "debt_to_equity", lambda value, limit: value <= limit),
        ("min_momentum_12m", "momentum_12m", lambda value, limit: value >= limit),
        ("max_volatility_90d", "volatility_90d", lambda value, limit: value <= limit),
        ("min_dividend_yield", "dividend_yield", lambda value, limit: value >= limit),
        ("min_average_volume", "average_volume", lambda value, limit: value >= limit),
    )
    for filter_name, metric, predicate in checks:
        limit = filters.get(filter_name)
        if limit is None:
            continue
        value = snapshot.get(metric)
        if value is None or isinstance(value, bool):
            missing.append(metric)
        elif not predicate(float(value), float(limit)):
            reasons.append(filter_name)
    sector = filters.get("sector")
    if sector:
        value = snapshot.get("sector")
        if not value:
            missing.append("sector")
        elif str(sector).casefold() not in str(value).casefold():
            reasons.append("sector")
    return reasons, sorted(set(missing))


def screen_universe(
    market: str = "US",
    *,
    exchange: str | None = None,
    offset: int = 0,
    limit: int = MAX_SCREENER_PAGE_SIZE,
    timeout_seconds: float = 12.0,
    filters: Mapping[str, Any] | None = None,
    universe_provider: UniverseProvider | None = None,
    snapshot_provider: Any = None,
) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or offset > MAX_UNIVERSE_SYMBOLS:
        raise ValueError("offset must be between 0 and 50000")
    if type(limit) is not int or not 1 <= limit <= MAX_SCREENER_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_SCREENER_PAGE_SIZE}")
    if not 0.5 <= float(timeout_seconds) <= 15.0:
        raise ValueError("timeout_seconds must be between 0.5 and 15")
    market = market.strip().upper()
    started = time.monotonic()
    provider = universe_provider or UniverseProvider(
        os.environ.get("TRADINGDYOR_UNIVERSE_CACHE", ".tradingdyor/universes"),
        timeout=min(8.0, float(timeout_seconds) / 2.0),
    )
    universe = provider.load(market)
    if universe["status"] == "unavailable":
        return {
            "status": "unavailable", "market": market, "exchange": exchange,
            "candidate_count": 0, "included": [], "excluded": [],
            "error_type": universe.get("error_type"), "advisory_only": True,
        }
    symbols = universe["symbols"]
    if exchange:
        wanted = exchange.strip().upper().replace(" ", "_")
        symbols = [row for row in symbols if row.get("exchange", "").upper() == wanted]
    page = symbols[offset:offset + limit]
    remaining = max(0.0, float(timeout_seconds) - (time.monotonic() - started))
    if remaining <= 0:
        return {
            "status": "partial", "market": market, "exchange": exchange,
            "universe_status": universe["status"],
            "universe_cache_status": universe["cache_status"],
            "universe_fetched_at": universe.get("fetched_at"),
            "universe_sources": universe.get("source_urls", []),
            "offset": offset, "next_offset": offset + len(page),
            "page_size": len(page), "candidate_count": len(symbols),
            "screened_count": 0, "included": [],
            "excluded": [{**row, "status": "timeout", "error_type": "SharedDeadline"} for row in page],
            "filters": dict(filters or {}), "timed_out": len(page),
            "capacity_limited": 0, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "advisory_only": True,
        }
    selected_filters = dict(filters or {})
    loader = snapshot_provider or _cached_snapshot
    futures = {}
    capacity_limited = []
    for row in page:
        ticker = row["ticker"]
        if snapshot_provider is None:
            acquired = _SNAPSHOT_SLOTS.acquire(blocking=False)
            if not acquired:
                capacity_limited.append(ticker)
                continue
            future = _SNAPSHOT_EXECUTOR.submit(_snapshot_with_slot, ticker)
        else:
            future = _SNAPSHOT_EXECUTOR.submit(loader, ticker)
        futures[future] = row
    done, pending = wait(futures, timeout=remaining)
    included, excluded = [], []
    for future in done:
        row = futures[future]
        try:
            snapshot = future.result()
            reasons, missing = _filter_reasons(snapshot, selected_filters)
            candidate = {
                **row, "snapshot": snapshot,
                "missing_metrics": missing,
                "as_of": snapshot.get("price_as_of"),
                "retrieved_at": snapshot.get("retrieved_at"),
                "currency": snapshot.get("currency"),
            }
            if reasons or missing:
                excluded.append({**candidate, "exclusion_reasons": reasons + [f"missing:{x}" for x in missing]})
            else:
                included.append(candidate)
        except Exception as exc:
            excluded.append({**row, "status": "unavailable", "error_type": type(exc).__name__})
    for future in pending:
        row = futures[future]
        excluded.append({**row, "status": "timeout", "error_type": "ProviderTimeout"})
    for ticker in capacity_limited:
        excluded.append({"ticker": ticker, "status": "not_started", "error_type": "ProviderCapacity"})
    status = "partial" if pending or capacity_limited or universe["status"] == "stale" else "available"
    return {
        "status": status,
        "market": market,
        "exchange": exchange or ("US_ALL" if market == "US" else "NSE"),
        "universe_status": universe["status"],
        "universe_cache_status": universe["cache_status"],
        "universe_fetched_at": universe.get("fetched_at"),
        "universe_sources": universe.get("source_urls", []),
        "offset": offset,
        "next_offset": offset + len(page),
        "page_size": len(page),
        "candidate_count": len(symbols),
        "screened_count": len(done),
        "included": included,
        "excluded": excluded,
        "filters": selected_filters,
        "timed_out": len(pending),
        "capacity_limited": len(capacity_limited),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "advisory_only": True,
    }


def _snapshot_with_slot(ticker: str) -> dict[str, Any]:
    try:
        return _cached_snapshot(ticker)
    finally:
        _SNAPSHOT_SLOTS.release()


__all__ = ["UniverseProvider", "UniverseUnavailable", "screen_universe"]
