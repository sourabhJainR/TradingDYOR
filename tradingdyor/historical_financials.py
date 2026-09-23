from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import requests


@dataclass(frozen=True)
class FinancialObservation:
    ticker: str
    concept: str
    value: float
    unit: str
    period_end: str
    filed: str
    form: str
    accession: str


def _facts_for_unit(fact: dict, preferred: str | None = None) -> list[dict]:
    units = fact.get("units", {})
    if preferred and preferred in units:
        return units[preferred]
    return next(iter(units.values()), [])


def normalize_companyfacts(ticker: str, facts: dict, concepts: list[str]) -> list[FinancialObservation]:
    out: list[FinancialObservation] = []
    facts_root = facts.get("facts", {})
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept in concepts:
            fact = facts_root.get(taxonomy, {}).get(concept)
            if not fact:
                continue
            unit = next(iter(fact.get("units", {})), "")
            for row in _facts_for_unit(fact):
                if not row.get("filed") or not row.get("end"):
                    continue
                out.append(
                    FinancialObservation(
                        ticker=ticker.upper(),
                        concept=concept,
                        value=float(row["val"]),
                        unit=unit,
                        period_end=row["end"],
                        filed=row["filed"],
                        form=row.get("form", ""),
                        accession=row.get("accn", ""),
                    )
                )
    return sorted(out, key=lambda x: (x.filed, x.period_end, x.concept))


def sec_companyfacts(cik: str, user_agent: str = "TradingDYOR research/0.4") -> dict:
    cik10 = str(cik).zfill(10)
    response = requests.get(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
        headers={"User-Agent": user_agent},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()
