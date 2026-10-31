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
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    price_as_of: datetime | None = None
    currency: str | None = None
    price: float | None = None
    market_cap: float | None = None
    average_volume: float | None = None
    dividend_yield: float | None = None
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
    market_regime: str | None = None
    regime_score: float | None = None
    regime_stress: float | None = None
    macro_pressure: float | None = None
    event_pressure: float | None = None
    news_sentiment_status: str = "unscored"
    news_sentiment_score: float | None = None
    news_sentiment_confidence: float = 0.0
    news_sample_count: int = 0
    news_publisher_count: int = 0
    expected_return_edge: float | None = None
    expected_risk: float | None = None
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
    thesis: str = ""
    strategy_scores: dict[str, float] = {}
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
