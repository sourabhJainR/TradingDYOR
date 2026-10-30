from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

import pandas as pd


@dataclass(frozen=True)
class Observation:
    ticker: str
    as_of: datetime
    metric: str
    value: float | str | None
    source: str
    source_url: str
    confidence: float = 0.0
    available_at: datetime | None = None
    published_at: datetime | None = None
    observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    provider: str = ""
    content_digest: str = ""
    extraction_version: str = ""

    def availability_time(self) -> datetime | None:
        """Return a source-time anchor; retrieval time is deliberately excluded."""
        return self.available_at or self.published_at or self.observed_at


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat() if normalized else None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


class PointInTimeStore:
    """SQLite-backed evidence observations filtered by source availability time."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                metric TEXT NOT NULL,
                value_json TEXT,
                source TEXT NOT NULL,
                source_url TEXT NOT NULL,
                confidence REAL NOT NULL,
                as_of TEXT NOT NULL,
                available_at TEXT,
                published_at TEXT,
                observed_at TEXT,
                retrieved_at TEXT,
                provider TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                extraction_version TEXT NOT NULL
            )
        """)
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_ticker_available "
            "ON observations(ticker, available_at, metric)"
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def add(self, row: Observation) -> bool:
        if not row.ticker.strip() or not row.metric.strip() or not row.source.strip():
            raise ValueError("ticker, metric and source are required")
        if not row.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an HTTP(S) URL")
        if not 0.0 <= float(row.confidence) <= 1.0:
            raise ValueError("confidence must be between zero and one")
        available_at = _iso(row.available_at)
        as_of = _iso(row.as_of)
        if as_of is None:
            raise ValueError("as_of is required")
        value_json = json.dumps(row.value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = row.content_digest or hashlib.sha256(
            json.dumps(
                [row.ticker.upper(), row.metric, value_json, row.source, row.source_url,
                 available_at, row.extraction_version],
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        observation_id = hashlib.sha256(
            f"{row.ticker.upper()}|{row.metric}|{row.source}|{digest}".encode("utf-8")
        ).hexdigest()
        with self._lock:
            cursor = self._connection.execute(
                """INSERT OR IGNORE INTO observations (
                observation_id,ticker,metric,value_json,source,source_url,confidence,
                as_of,available_at,published_at,observed_at,retrieved_at,provider,
                content_digest,extraction_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                observation_id, row.ticker.upper(), row.metric, value_json, row.source,
                row.source_url, float(row.confidence), as_of, available_at,
                _iso(row.published_at), _iso(row.observed_at), _iso(row.retrieved_at),
                row.provider, digest, row.extraction_version,
                ),
            )
            self._connection.commit()
            return cursor.rowcount == 1

    def latest(self, ticker: str, as_of: datetime | None = None) -> list[Observation]:
        cutoff = _utc(as_of or datetime.now(timezone.utc))
        with self._lock:
            rows = self._connection.execute(
                """SELECT ticker,metric,value_json,source,source_url,confidence,as_of,
                          available_at,published_at,observed_at,retrieved_at,provider,
                          content_digest,extraction_version
                   FROM observations WHERE ticker=?""",
                (ticker.upper(),),
            ).fetchall()
        eligible: list[tuple[datetime, Observation]] = []
        for row in rows:
            (
                symbol, metric, value_json, source, source_url, confidence, as_of_raw,
                available_raw, published_raw, observed_raw, retrieved_raw, provider,
                content_digest, extraction_version,
            ) = row
            if available_raw is not None:
                available = _parse_time(available_raw)
            elif published_raw is not None:
                available = _parse_time(published_raw)
            else:
                available = _parse_time(observed_raw)
            # Never use as_of or retrieved_at as a fallback availability time.
            if available is None or available > cutoff:
                continue
            value = json.loads(value_json) if value_json is not None else None
            observation = Observation(
                ticker=symbol,
                as_of=_parse_time(as_of_raw) or available,
                metric=metric,
                value=value,
                source=source,
                source_url=source_url,
                confidence=confidence,
                available_at=_parse_time(available_raw),
                published_at=_parse_time(published_raw),
                observed_at=_parse_time(observed_raw),
                retrieved_at=_parse_time(retrieved_raw),
                provider=provider,
                content_digest=content_digest,
                extraction_version=extraction_version,
            )
            eligible.append((available, observation))
        latest: dict[str, tuple[datetime, Observation]] = {}
        for available, observation in sorted(eligible, key=lambda item: item[0]):
            latest[observation.metric] = (available, observation)
        return [item[1] for item in latest.values()]

    def frame(self, ticker: str, as_of: datetime | None = None) -> pd.DataFrame:
        return pd.DataFrame([row.__dict__ for row in self.latest(ticker, as_of)])

    def forward_return(
        self,
        prices: pd.Series,
        signal_date: pd.Timestamp,
        months: int = 12,
        entry_lag_sessions: int = 1,
    ) -> float | None:
        """Measure forward return from the first eligible session after the signal."""
        if entry_lag_sessions < 0:
            raise ValueError("entry_lag_sessions cannot be negative")
        if months < 1:
            raise ValueError("months must be at least one")
        p = prices.dropna().sort_index()
        if p.empty:
            return None
        signal = pd.Timestamp(signal_date)
        if getattr(p.index, "tz", None) is not None and signal.tzinfo is None:
            signal = signal.tz_localize(p.index.tz)
        elif getattr(p.index, "tz", None) is None and signal.tzinfo is not None:
            signal = signal.tz_convert(None)
        if entry_lag_sessions == 0:
            eligible = p[p.index >= signal]
        else:
            eligible = p[p.index > signal]
        if len(eligible) < max(1, entry_lag_sessions):
            return None
        entry = float(eligible.iloc[max(0, entry_lag_sessions - 1)])
        target_date = signal + pd.DateOffset(months=months)
        future = p[p.index >= target_date]
        return None if future.empty or entry == 0 else float(future.iloc[0] / entry - 1)
