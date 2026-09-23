from __future__ import annotations
import re
from dataclasses import dataclass
import requests

@dataclass(frozen=True)
class Filing:
    ticker: str
    form: str
    filed: str
    accession: str
    primary_document: str
    url: str

def sec_filings(ticker: str, limit: int = 20) -> list[Filing]:
    ticker = ticker.upper().strip()
    if not ticker: return []
    headers = {"User-Agent": "TradingDYOR research/0.3"}
    mapping = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=20).json()
    cik = next((str(v["cik_str"]).zfill(10) for v in mapping.values() if v["ticker"].upper() == ticker), None)
    if not cik: return []
    data = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers, timeout=20).json()
    recent = data.get("filings", {}).get("recent", {})
    out = []
    for form, filed, acc, doc in zip(recent.get("form", []), recent.get("filingDate", []), recent.get("accessionNumber", []), recent.get("primaryDocument", [])):
        if len(out) >= limit: break
        if form not in {"10-K", "10-Q", "8-K", "20-F", "6-K"}: continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
        out.append(Filing(ticker, form, filed, acc, doc, url))
    return out

def filing_signal_tags(text: str) -> list[str]:
    terms = {"guidance": r"\bguidance\b|\boutlook\b", "acquisition": r"\bacquisition\b|\bmerger\b|\bdefinitive agreement\b", "litigation": r"\blitigation\b|\blawsuit\b|\bcomplaint\b", "restructuring": r"\brestructuring\b|\bworkforce reduction\b|\blayoff\b", "capital_return": r"\bdividend\b|\brepurchase\b|\bbuyback\b", "cyber": r"\bcybersecurity\b|\bdata breach\b"}
    return [name for name, pattern in terms.items() if re.search(pattern, text, re.I)]
