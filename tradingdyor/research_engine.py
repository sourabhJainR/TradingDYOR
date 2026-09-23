from __future__ import annotations

from .market_data import snapshot_ticker
from .decision import decide
from .market_intelligence import market_intelligence


def research_ticker(ticker: str):
    ticker = ticker.upper()
    snapshot = snapshot_ticker(ticker)
    intelligence = market_intelligence(ticker)

    insider_net = intelligence["insiders"]["signal"].get("net_shares")
    if insider_net is not None:
        snapshot.insider_net_buy = float(insider_net)
    snapshot.evidence_count += int(intelligence["filing_activity"]["count"] > 0)
    snapshot.evidence_coverage = min(
        1.0,
        0.45 + 0.15 * min(1, intelligence["evidence_coverage"]),
    )

    decision = decide(snapshot)
    return {
        "snapshot": snapshot.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "market_intelligence": intelligence,
    }


def research_universe(tickers: list[str]):
    results = []
    for ticker in dict.fromkeys(tickers):
        try:
            results.append(research_ticker(ticker))
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})
    valid = [r["decision"] for r in results if "decision" in r]
    return {
        "results": results,
        "buy": sorted([x for x in valid if x["action"] == "BUY"], key=lambda x: x["score"], reverse=True)[:5],
        "hold": sorted([x for x in valid if x["action"] == "HOLD"], key=lambda x: x["score"], reverse=True)[:5],
        "sell": sorted([x for x in valid if x["action"] == "SELL"], key=lambda x: x["score"])[:5],
    }
