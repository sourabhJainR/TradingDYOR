from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import re

from .regime_intelligence import EventForecast, EventMemory


CATEGORIES = ("geopolitical", "government", "macro", "sector", "company")


def event_id(category: str, entity: str, expected_at: str) -> str:
    return sha256(f"{category}|{entity}|{expected_at}".encode()).hexdigest()[:20]


def build_forecast(category: str, entity: str, expected_at: str, window_days: int,
                   importance: float, probability: float, expected_direction: float,
                   source: str) -> EventForecast:
    if category not in CATEGORIES:
        raise ValueError(f"unsupported event category: {category}")
    expected = datetime.fromisoformat(expected_at.replace("Z", "+00:00"))
    window = max(1, int(window_days))
    return EventForecast(
        event_id=event_id(category, entity, expected_at),
        category=category, entity=entity, expected_at=expected_at,
        window_start=(expected - timedelta(days=window)).isoformat(),
        window_end=(expected + timedelta(days=window)).isoformat(),
        importance=max(0.0, min(1.0, importance)),
        probability=max(0.0, min(1.0, probability)),
        expected_direction=max(-1.0, min(1.0, expected_direction)),
        source=source, created_at=datetime.now(timezone.utc).isoformat(),
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


def event_pressure(memory: EventMemory, ticker: str | None = None) -> float:
    now = datetime.now(timezone.utc)
    pressure = 0.0
    for event in memory.events:
        if event.observed_at or event.importance <= 0:
            continue
        expected = datetime.fromisoformat(event.expected_at.replace("Z", "+00:00"))
        window_start = datetime.fromisoformat(event.window_start.replace("Z", "+00:00"))
        window_end = datetime.fromisoformat(event.window_end.replace("Z", "+00:00"))
        if window_start <= now <= window_end:
            pressure = max(pressure, event.importance * event.probability)
        else:
            days = min(abs((window_start - now).total_seconds()), abs((window_end - now).total_seconds())) / 86400.0
            if days <= 14:
                pressure = max(pressure, event.importance * event.probability * (1.0 - min(days / 14.0, 1.0)))
    return min(1.0, pressure)
