from __future__ import annotations
from datetime import datetime, timezone
from dataclasses import dataclass
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

class PointInTimeStore:
    """In-memory point-in-time store. Replaceable with Postgres/Parquet without changing callers."""

    def __init__(self):
        self._rows: list[Observation] = []

    def add(self, row: Observation):
        self._rows.append(row)

    def latest(self, ticker: str, as_of: datetime | None = None) -> list[Observation]:
        cutoff = as_of or datetime.now(timezone.utc)
        rows=[r for r in self._rows if r.ticker==ticker and r.as_of<=cutoff]
        latest={}
        for r in sorted(rows,key=lambda x:x.as_of):
            latest[r.metric]=r
        return list(latest.values())

    def frame(self, ticker: str, as_of: datetime | None = None) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in self.latest(ticker,as_of)])

    def forward_return(self, prices: pd.Series, signal_date: pd.Timestamp, months: int = 12) -> float | None:
        p=prices.dropna().sort_index()
        if p.empty: return None
        start=p[p.index>=signal_date]
        if start.empty: return None
        entry=float(start.iloc[0])
        target_date=signal_date+pd.DateOffset(months=months)
        future=p[p.index>=target_date]
        return None if future.empty or entry==0 else float(future.iloc[0]/entry-1)
