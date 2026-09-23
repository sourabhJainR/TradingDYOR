from __future__ import annotations
from datetime import datetime, timezone
import yfinance as yf
from .models import SecuritySnapshot

def snapshot_ticker(ticker: str) -> SecuritySnapshot:
    t=yf.Ticker(ticker)
    info=t.info
    hist=t.history(period="2y",auto_adjust=True)
    close=hist["Close"].dropna()
    momentum=None
    volatility=None
    if len(close)>=252:
        momentum=float(close.iloc[-1]/close.iloc[-252]-1)
    if len(close)>=90:
        volatility=float(close.pct_change().tail(90).std()*90**0.5)

    return SecuritySnapshot(
        ticker=ticker.upper(),
        as_of=datetime.now(timezone.utc),
        price=float(close.iloc[-1]) if len(close) else info.get("currentPrice"),
        market_cap=info.get("marketCap"),
        pe=info.get("trailingPE"),
        ps=info.get("priceToSalesTrailing12Months"),
        revenue_growth=info.get("revenueGrowth"),
        earnings_growth=info.get("earningsGrowth"),
        roe=info.get("returnOnEquity"),
        debt_to_equity=info.get("debtToEquity"),
        free_cash_flow=info.get("freeCashflow"),
        momentum_12m=momentum,
        volatility_90d=volatility,
        sector=info.get("sector"),
        company_name=info.get("longName") or info.get("shortName"),
        evidence_count=1,
        evidence_coverage=0.45,
    )
