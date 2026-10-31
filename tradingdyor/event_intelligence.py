from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import math
import re

from .regime_intelligence import EventForecast, EventMemory


CATEGORIES = ("geopolitical", "government", "macro", "sector", "company")


def event_id(category: str, entity: str, expected_at: str) -> str:
    return sha256(f"{category}|{entity}|{expected_at}".encode()).hexdigest()[:20]


def build_forecast(category: str, entity: str, expected_at: str, window_days: int,
                   importance: float, probability: float, expected_direction: float,
                   source: str, affected_metrics: list[str] | None = None,
                   thesis_impacts: list[str] | None = None) -> EventForecast:
    category = str(category).strip().lower()
    entity = str(entity).strip()
    source = str(source).strip()
    if category not in CATEGORIES:
        raise ValueError(f"unsupported event category: {category}")
    if not entity or len(entity) > 120:
        raise ValueError("event entity must contain 1 to 120 characters")
    if not source or len(source) > 500:
        raise ValueError("event source must contain 1 to 500 characters")
    if type(window_days) is not int or not 1 <= window_days <= 90:
        raise ValueError("window_days must be between 1 and 90")
    expected = datetime.fromisoformat(str(expected_at).replace("Z", "+00:00"))
    if expected.tzinfo is None:
        raise ValueError("expected_at must include an explicit timezone")
    expected = expected.astimezone(timezone.utc)
    normalized_expected_at = expected.isoformat()
    values = [float(importance), float(probability), float(expected_direction)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("event numeric fields must be finite")
    if not 0.0 <= values[0] <= 1.0:
        raise ValueError("importance must be between 0 and 1")
    if not 0.0 <= values[1] <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    if not -1.0 <= values[2] <= 1.0:
        raise ValueError("expected_direction must be between -1 and 1")
    if affected_metrics is not None and not isinstance(affected_metrics, (list, tuple)):
        raise ValueError("affected_metrics must be a list of labels")
    if thesis_impacts is not None and not isinstance(thesis_impacts, (list, tuple)):
        raise ValueError("thesis_impacts must be a list of labels")
    metrics = list(dict.fromkeys(str(x).strip() for x in (affected_metrics or []) if str(x).strip()))
    impacts = list(dict.fromkeys(str(x).strip() for x in (thesis_impacts or []) if str(x).strip()))
    if len(metrics) > 10 or len(impacts) > 10:
        raise ValueError("at most 10 affected metrics and thesis impacts are allowed")
    if any(len(x) > 120 for x in metrics + impacts):
        raise ValueError("event metric and thesis impact labels must be at most 120 characters")
    return EventForecast(
        event_id=event_id(category, entity, normalized_expected_at),
        category=category, entity=entity, expected_at=normalized_expected_at,
        window_start=(expected - timedelta(days=window_days)).isoformat(),
        window_end=(expected + timedelta(days=window_days)).isoformat(),
        importance=values[0], probability=values[1], expected_direction=values[2],
        source=source, created_at=datetime.now(timezone.utc).isoformat(),
        affected_metrics=metrics, thesis_impacts=impacts,
    )

def extract_event_candidates(text: str, category: str, entity: str, source: str) -> list[EventForecast]:
    # Candidate extraction deliberately produces forecasts only when a date is present.
    # It does not invent a date from vague language.
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    results = []
    for value in dates[:10]:
        results.append(build_forecast(category, entity, f"{value}T12:00:00+00:00",
                                       1, 0.5, 0.5, 0.0, source))
    return results


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def event_pressure(memory: EventMemory, ticker: str | None = None) -> float:
    now = datetime.now(timezone.utc)
    pressure = 0.0
    for event in memory.events:
        if event.observed_at or event.importance <= 0:
            continue
        if ticker and event.category == "company":
            event_entity = event.entity.strip().upper()
            symbol = ticker.strip().upper()
            if event_entity not in {symbol, symbol.removesuffix(".NS"), symbol.removesuffix(".BO")}:
                continue
        try:
            window_start = _utc_datetime(event.window_start)
            window_end = _utc_datetime(event.window_end)
        except (TypeError, ValueError):
            continue
        if window_start <= now <= window_end:
            pressure = max(pressure, event.importance * event.probability)
        else:
            days = min(abs((window_start - now).total_seconds()), abs((window_end - now).total_seconds())) / 86400.0
            if days <= 14:
                pressure = max(pressure, event.importance * event.probability * (1.0 - min(days / 14.0, 1.0)))
    return min(1.0, pressure)
