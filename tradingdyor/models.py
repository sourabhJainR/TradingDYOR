from datetime import datetime, timezone
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    source: str
    url: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    title: str = ""
    excerpt: str = ""
    confidence: float = 0.0
    extraction_method: str = "browser"

class SecuritySnapshot(BaseModel):
    ticker: str
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    price: float | None = None
    market_cap: float | None = None
    pe: float | None = None
    ps: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None
    insider_net_buy: float | None = None
    institutional_flow: float | None = None
    momentum_12m: float | None = None
    volatility_90d: float | None = None
    sector: str | None = None
    company_name: str | None = None
    evidence_count: int = 0
    evidence_coverage: float = 0.0

class Signal(BaseModel):
    ticker: str
    strategy: str
    score: float
    horizon_months: int
    rationale: list[str] = []

class Decision(BaseModel):
    ticker: str
    action: str
    score: float
    confidence: float
    evidence_coverage: float
    strategy_agreement: float
    key_reasons: list[str] = []
    risks: list[str] = []
    invalidation: list[str] = []
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
