from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
import xml.etree.ElementTree as ET

import requests
import yfinance as yf

from .corporate_actions import normalize_actions
from .earnings import EarningsObservation, earnings_signal
from .filings import sec_filings
from .insiders import InsiderTransaction, insider_signal, normalize_insider_rows
from .sector import SectorState, sector_score

SEC_HEADERS = {"User-Agent": "TradingDYOR research/0.5 contact@example.com"}


def _cik_for_ticker(ticker: str) -> str | None:
    data = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS, timeout=20).json()
    wanted = ticker.upper()
    for row in data.values():
        if str(row.get("ticker", "")).upper() == wanted:
            return str(row["cik_str"]).zfill(10)
    return None


def _archive_url(cik: str, accession: str, document: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"


def sec_insider_transactions(ticker: str, limit: int = 20) -> list[InsiderTransaction]:
    """Best-effort SEC Form 4 parser; only open-market purchases/sales are treated as directional."""
    cik = _cik_for_ticker(ticker)
    if not cik:
        return []
    submissions = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers=SEC_HEADERS,
        timeout=20,
    ).json()
    recent = submissions.get("filings", {}).get("recent", {})
    rows = []
    for i, form in enumerate(recent.get("form", [])):
        if form != "4":
            continue
        rows.append({
            "filing_date": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "primary_document": recent["primaryDocument"][i],
        })
        if len(rows) >= limit:
            break

    out: list[InsiderTransaction] = []
    for row in rows:
        try:
            xml_text = requests.get(
                _archive_url(cik, row["accession"], row["primary_document"]),
                headers=SEC_HEADERS,
                timeout=20,
            ).text
            root = ET.fromstring(xml_text)
            ns = {"x": "http://www.sec.gov/edgar/thirteenf"}
            for node in root.findall(".//nonDerivativeTransaction"):
                code = (node.findtext(".//transactionCoding/transactionCode") or "").strip()
                if code not in {"P", "S"}:
                    continue
                shares = node.findtext(".//transactionAmounts/transactionShares/value")
                price = node.findtext(".//transactionAmounts/transactionPricePerShare/value")
                insider = node.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or ""
                out.append(InsiderTransaction(
                    ticker=ticker.upper(),
                    filing_date=row["filing_date"],
                    insider=insider,
                    form="4",
                    shares=float(shares) if shares else None,
                    price=float(price) if price else None,
                    transaction_code=code,
                ))
        except (requests.RequestException, ET.ParseError, ValueError):
            continue
    return out


def earnings_history(ticker: str, limit: int = 8) -> list[EarningsObservation]:
    try:
        frame = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception:
        return []
    if frame is None or frame.empty:
        return []
    out = []
    for idx, row in frame.iterrows():
        reported = row.get("Reported EPS")
        estimate = row.get("EPS Estimate")
        surprise = row.get("Surprise(%)")
        out.append(EarningsObservation(
            ticker=ticker.upper(),
            period=str(getattr(idx, "date", lambda: idx)()),
            reported=float(reported) if reported == reported else None,
            estimate=float(estimate) if estimate == estimate else None,
            surprise_pct=float(surprise) if surprise == surprise else None,
        ))
    return out


def corporate_actions_history(ticker: str) -> list[dict]:
    try:
        actions = yf.Ticker(ticker).actions
    except Exception:
        return []
    if actions is None or actions.empty:
        return []
    rows = []
    for idx, row in actions.iterrows():
        if row.get("Dividends", 0):
            rows.append({"ticker": ticker.upper(), "event_date": str(idx.date()), "kind": "dividend", "cash": float(row["Dividends"])})
        if row.get("Stock Splits", 0):
            rows.append({"ticker": ticker.upper(), "event_date": str(idx.date()), "kind": "split", "ratio": float(row["Stock Splits"])})
    return [asdict(x) for x in normalize_actions(rows)]


def market_intelligence(ticker: str) -> dict:
    ticker = ticker.upper()
    insider_rows = sec_insider_transactions(ticker)
    earnings_rows = earnings_history(ticker)
    actions = corporate_actions_history(ticker)
    filings = sec_filings(ticker, limit=20)
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector") or "Unknown"
    except Exception:
        sector = "Unknown"

    earnings = earnings_signal(earnings_rows)
    insider = insider_signal(insider_rows)
    coverage_parts = [
        bool(insider_rows),
        bool(earnings_rows),
        bool(actions),
        bool(filings),
    ]
    coverage = sum(coverage_parts) / len(coverage_parts)
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "insiders": {"signal": insider, "observations": [asdict(x) for x in insider_rows]},
        "earnings": {"signal": earnings, "observations": [asdict(x) for x in earnings_rows]},
        "corporate_actions": {"count": len(actions), "recent": actions[-12:]},
        "filing_activity": {
            "count": len(filings),
            "recent": [{"form": f.form, "filed": f.filed, "document": f.primary_document, "url": f.url} for f in filings],
        },
        "sector": {"name": sector, "score": None, "status": "identified"},
        "evidence_coverage": coverage,
        "evidence_policy": "point-in-time",
    }
