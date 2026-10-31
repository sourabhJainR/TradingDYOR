from __future__ import annotations
from datetime import datetime, timezone
import math
import yfinance as yf
from .models import SecuritySnapshot

def _finite_number(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def snapshot_ticker(ticker: str) -> SecuritySnapshot:
    t=yf.Ticker(ticker)
    info=t.info
    hist=t.history(period="2y",auto_adjust=True)
    close=hist["Close"].dropna()
    momentum=None
    volatility=None
    price_as_of = None
    if len(close):
        last_time = close.index[-1].to_pydatetime()
        price_as_of = last_time.replace(tzinfo=timezone.utc) if last_time.tzinfo is None else last_time.astimezone(timezone.utc)
    retrieved_at = datetime.now(timezone.utc)
    if len(close)>=252:
        momentum=float(close.iloc[-1]/close.iloc[-252]-1)
    if len(close)>=90:
        volatility=float(close.pct_change().tail(90).std()*90**0.5)

    return SecuritySnapshot(
        ticker=ticker.upper(),
        as_of=retrieved_at,
        retrieved_at=retrieved_at,
        price_as_of=price_as_of,
        currency=info.get("currency"),
        price=_finite_number(close.iloc[-1]) if len(close) else _finite_number(info.get("currentPrice")),
        market_cap=_finite_number(info.get("marketCap")),
        average_volume=_finite_number(info.get("averageVolume")),
        dividend_yield=_finite_number(info.get("dividendYield")),
        pe=_finite_number(info.get("trailingPE")),
        ps=_finite_number(info.get("priceToSalesTrailing12Months")),
        revenue_growth=_finite_number(info.get("revenueGrowth")),
        earnings_growth=_finite_number(info.get("earningsGrowth")),
        roe=_finite_number(info.get("returnOnEquity")),
        debt_to_equity=_finite_number(info.get("debtToEquity")),
        free_cash_flow=_finite_number(info.get("freeCashflow")),
        momentum_12m=_finite_number(momentum),
        volatility_90d=_finite_number(volatility),
        sector=info.get("sector"),
        company_name=info.get("longName") or info.get("shortName"),
        evidence_count=1,
        evidence_coverage=0.45,
    )
