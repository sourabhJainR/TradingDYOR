from __future__ import annotations
from dataclasses import dataclass
from .filings import Filing

@dataclass(frozen=True)
class Event:
    ticker: str
    event_date: str
    kind: str
    source_url: str
    source: str = "SEC"

def filing_events(filings: list[Filing]) -> list[Event]:
    return [Event(f.ticker, f.filed, f.form, f.url) for f in filings]

def corporate_action_keywords() -> tuple[str, ...]:
    return ("dividend", "split", "reverse split", "buyback", "offering", "spinoff", "merger")
