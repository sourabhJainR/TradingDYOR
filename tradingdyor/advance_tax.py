from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
import re
import requests


OFFICIAL_SOURCES = (
    "https://www.incometaxindia.gov.in/",
    "https://www.incometax.gov.in/",
    "https://www.pib.gov.in/",
)


@dataclass(frozen=True)
class AdvanceTaxSignal:
    market: str
    period: str
    collection: float | None
    yoy_growth: float | None
    corporate_growth: float | None
    personal_growth: float | None
    as_of: str
    source: str
    confidence: float
    interpretation: str


def _number(text: str) -> float | None:
    match = re.search(r"([0-9][0-9,.]*)\s*(?:lakh\s*crore|crore|%)?", text, re.I)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def from_official_observation(period: str, collection: float | None, yoy_growth: float | None,
                              corporate_growth: float | None = None,
                              personal_growth: float | None = None,
                              source: str = OFFICIAL_SOURCES[0]) -> dict:
    # Advance-tax is a leading tax-flow signal, not a direct proxy for listed-company earnings.
    confidence = 0.85 if corporate_growth is not None else 0.65
    interpretation = "growth-positive" if (yoy_growth or 0) > 0 else "growth-softening"
    if corporate_growth is not None:
        interpretation = "corporate-profit-tax momentum positive" if corporate_growth > 0 else "corporate-profit-tax momentum softening"
    return asdict(AdvanceTaxSignal(
        market="INDIA", period=period, collection=collection, yoy_growth=yoy_growth,
        corporate_growth=corporate_growth, personal_growth=personal_growth,
        as_of=datetime.now(timezone.utc).isoformat(), source=source,
        confidence=confidence, interpretation=interpretation,
    ))


def tax_calendar(year: int) -> list[dict]:
    return [
        {"installment": 1, "date": f"{year}-06-15", "percent": 15},
        {"installment": 2, "date": f"{year}-09-15", "percent": 45},
        {"installment": 3, "date": f"{year}-12-15", "percent": 75},
        {"installment": 4, "date": f"{year+1}-03-15", "percent": 100},
    ]


def official_source_status() -> dict:
    return {
        "sources": list(OFFICIAL_SOURCES),
        "note": "The system stores published advance-tax observations; it does not claim access to confidential taxpayer filings or PAN-level data.",
        "purpose": "leading macro/corporate-profit tax-flow indicator",
    }
