from pathlib import Path
from datetime import datetime, timezone
import os
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .models import SecuritySnapshot
from .decision import decide
from .sources import SOURCES
from .research import rank_universe
from .learning import RoutingPolicy
from .research_engine import research_ticker, research_universe
from .store import count
from .filings import sec_filings, filing_signal_tags
from .counterfactual import evaluate_branches
from .strategy_validation import walk_forward_strategies, summarize_strategy_walk_forward
from .experience import Experience, ExperienceMemory
from .outcome_learning import DecisionEpisode, OutcomeMemory, evaluate_episode, stable_episode_id
from .market_data import snapshot_ticker
from .market_intelligence import market_intelligence
from .institutional import parse_13f, summarize_positions
from .macro_adapter import live_macro, fred_series
from .sector_adapter import sector_state
from .patents import search_patents
from .decision_fabric import DecisionFabric
from .monthly_optimizer import build_monthly_recommendations
from .news_sentiment import fetch_company_news
from .point_in_time import Observation, PointInTimeStore
from .macro_intelligence import macro_state
from .regime_intelligence import EventMemory
from .event_intelligence import build_forecast, extract_event_candidates
from .advance_tax import from_official_observation, official_source_status, tax_calendar, AdvanceTaxMemory

from .research_graph import ResearchGraph
from .orchestrator import ResearchOrchestrator
from .research_collectors import COLLECTORS

app=FastAPI(title="TradingDYOR", version="0.5.0")
policy=RoutingPolicy.load()
experience=ExperienceMemory()
fabric=DecisionFabric(policy, experience)
outcomes=OutcomeMemory()
WEB_ROOT=Path(__file__).resolve().parent.parent / "web"

@app.get("/health")
def health():
    return {"status":"ok","sources":len(SOURCES),"evidence_records":count(),"ui":"spa"}

@app.get("/sources")
def sources(): return [s.__dict__ for s in SOURCES]

@app.get("/")
def spa(): return FileResponse(WEB_ROOT / "index.html")

@app.get("/brief/{ticker}")
def one_page_brief_app(ticker: str): return FileResponse(WEB_ROOT / "brief.html")

@app.post("/research/score")
def score(snapshot: SecuritySnapshot):
    if not 0 <= snapshot.evidence_coverage <= 1: raise HTTPException(400,"evidence_coverage must be between 0 and 1")
    return decide(snapshot).model_dump(mode="json")

@app.post("/research/universe")
def universe(snapshots: list[SecuritySnapshot]):
    if not snapshots: raise HTTPException(400,"at least one snapshot is required")
    return {k:[x.model_dump(mode="json") for x in v] for k,v in rank_universe(snapshots).items()}

@app.get("/research/screener")
def research_screener(
    market: str = "US",
    exchange: str | None = None,
    offset: int = 0,
    limit: int = 12,
    timeout_seconds: float = 12.0,
    sector: str | None = None,
    min_market_cap: float | None = None,
    max_pe: float | None = None,
    min_revenue_growth: float | None = None,
    min_earnings_growth: float | None = None,
    min_roe: float | None = None,
    max_debt_to_equity: float | None = None,
    min_momentum_12m: float | None = None,
    max_volatility_90d: float | None = None,
    min_dividend_yield: float | None = None,
    min_average_volume: float | None = None,
):
    from .universe import screen_universe
    filters = {
        "sector": sector,
        "min_market_cap": min_market_cap,
        "max_pe": max_pe,
        "min_revenue_growth": min_revenue_growth,
        "min_earnings_growth": min_earnings_growth,
        "min_roe": min_roe,
        "max_debt_to_equity": max_debt_to_equity,
        "min_momentum_12m": min_momentum_12m,
        "max_volatility_90d": max_volatility_90d,
        "min_dividend_yield": min_dividend_yield,
        "min_average_volume": min_average_volume,
    }
    try:
        result = screen_universe(
            market, exchange=exchange, offset=offset, limit=limit,
            timeout_seconds=timeout_seconds, filters=filters,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except OSError as exc:
        raise HTTPException(503, {"message": "screener cache is unavailable", "error_type": type(exc).__name__})
    if result.get("status") == "unavailable":
        raise HTTPException(503, {
            "message": "exchange universe unavailable and no usable cache exists",
            "error_type": result.get("error_type"),
        })
    return result


@app.get("/research/ticker/{ticker}")
def ticker(ticker: str): return research_ticker(ticker.upper())

@app.post("/research/live-universe")
def live_universe(tickers: list[str]):
    if not tickers: raise HTTPException(400,"at least one ticker is required")
    return research_universe([x.upper() for x in tickers[:200]])

@app.get("/research/evidence/{ticker}")
def research_evidence(ticker: str):
    filings = sec_filings(ticker.upper(), limit=20)
    return {
        "ticker": ticker.upper(),
        "filings": [f.__dict__ for f in filings],
        "event_tags": [
            {"form": f.form, "filed": f.filed, "tags": filing_signal_tags(f"{f.form} {f.primary_document}"), "url": f.url}
            for f in filings
        ],
    }

@app.get("/research/market-intelligence/{ticker}")
def research_market_intelligence(ticker: str):
    return market_intelligence(ticker.upper())



def _source_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _point_in_time_path():
    return os.environ.get("TRADINGDYOR_PIT_DB", ".tradingdyor/point_in_time.sqlite")


def _event_memory_path():
    return os.environ.get("TRADINGDYOR_EVENT_DB", ".tradingdyor/events.json")


def _persist_brief_observations(ticker, snapshot, events, news):
    now = datetime.now(timezone.utc)
    price_as_of = _source_datetime(snapshot.get("price_as_of"))
    snapshot_retrieved_at = _source_datetime(snapshot.get("retrieved_at")) or now
    news_retrieved_at = _source_datetime(news.get("retrieved_at"))
    added = 0
    eligible_added = 0
    try:
        store = PointInTimeStore(_point_in_time_path())
        try:
            def record(observation):
                nonlocal added, eligible_added
                inserted = store.add(observation)
                if inserted:
                    added += 1
                    anchor = _source_datetime(observation.availability_time())
                    eligible_added += int(anchor is not None and anchor <= now)

            market_url = f"https://finance.yahoo.com/quote/{ticker}"
            for metric in (
                "price", "market_cap", "average_volume", "dividend_yield", "pe", "revenue_growth", "roe",
                "debt_to_equity", "momentum_12m", "volatility_90d",
            ):
                value = snapshot.get(metric)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                record(Observation(
                    ticker=ticker, as_of=now, metric=metric, value=float(value),
                    source="market-data", source_url=market_url,
                    available_at=price_as_of if metric in {"price", "momentum_12m", "volatility_90d"} else None,
                    retrieved_at=snapshot_retrieved_at,
                    provider="yfinance", extraction_version="brief-v2",
                ))
            filing_rows = events.get("filings", {}).get("filings", [])
            for filing in filing_rows if isinstance(filing_rows, list) else []:
                if not isinstance(filing, dict):
                    continue
                url = filing.get("url")
                filed = _source_datetime(filing.get("filed"))
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                form = str(filing.get("form") or "filing")
                document = str(filing.get("document") or "")
                record(Observation(
                    ticker=ticker,
                    as_of=now,
                    metric=f"filing:{form}:{filed.isoformat() if filed else 'unknown'}",
                    value=document,
                    source="SEC",
                    source_url=url,
                    available_at=filed,
                    retrieved_at=now,
                    provider="SEC",
                    extraction_version="brief-v1",
                ))
            articles = news.get("articles", [])
            for article in articles if isinstance(articles, list) else []:
                if not isinstance(article, dict):
                    continue
                url = article.get("url")
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                providers = article.get("source_providers", [])
                source = "+".join(str(item) for item in providers) or "news"
                published_at = _source_datetime(article.get("publish_time"))
                observed_at = _source_datetime(article.get("seen_at"))
                story_id = str(article.get("story_id") or "")
                identity = story_id or hashlib.sha256(url.encode("utf-8")).hexdigest()
                record(Observation(
                    ticker=ticker,
                    as_of=now,
                    metric=f"news:{identity}",
                    value=str(article.get("title") or ""),
                    source=source,
                    source_url=url,
                    published_at=published_at,
                    observed_at=observed_at,
                    retrieved_at=news_retrieved_at or now,
                    provider=source,
                    content_digest=identity,
                    extraction_version="brief-v1",
                ))
        finally:
            store.close()
        status = "stored" if added and eligible_added == added else "partial" if added else "empty"
        return {
            "status": status,
            "observations_added": added,
            "eligible_observations_added": eligible_added,
            "error_type": None,
        }
    except Exception as exc:
        return {
            "status": "partial" if added else "unavailable",
            "observations_added": added,
            "eligible_observations_added": eligible_added,
            "error_type": type(exc).__name__,
        }


@app.get("/research/brief/{ticker}")
def research_brief(ticker: str, timespan: str = "7d"):
    """Build a partial-tolerant one-page brief from the research graph and current news."""
    symbol = ticker.strip().upper()
    if not symbol or len(symbol) > 15 or not symbol[0].isalnum() or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in symbol):
        raise HTTPException(400, "invalid ticker symbol")
    if timespan not in {"1d", "3d", "7d", "14d", "30d"}:
        raise HTTPException(400, "timespan must be one of 1d, 3d, 7d, 14d, 30d")
    brief_collectors = dict(COLLECTORS)
    brief_collectors["news"] = lambda value: COLLECTORS["news"](value, timespan=timespan)
    try:
        run = ResearchOrchestrator(fabric).run(symbol, brief_collectors)
    except Exception as exc:
        raise HTTPException(502, f"research graph unavailable: {type(exc).__name__}")
    nodes = run.graph.get("nodes", {}) if isinstance(run.graph, dict) else {}

    def node_result(name: str) -> dict:
        node = nodes.get(name, {})
        result = node.get("result") if isinstance(node, dict) else None
        return result if isinstance(result, dict) else {}

    fundamentals = node_result("fundamentals")
    snapshot = fundamentals.get("snapshot") or {}
    company_name = snapshot.get("company_name")
    decision = run.decision if isinstance(run.decision, dict) and run.decision.get("action") else {
        "ticker": symbol,
        "action": "HOLD",
        "score": 0.0,
        "confidence": 0.0,
        "evidence_coverage": 0.0,
        "strategy_agreement": 0.0,
        "thesis": "HOLD: company fundamentals were unavailable; no recommendation is supported.",
        "key_reasons": ["Fundamental snapshot unavailable"],
        "risks": ["Research providers did not return enough evidence"],
        "invalidation": [],
        "research_status": "unavailable",
        "missing_research_tasks": ["fundamentals"],
    }
    news_node = nodes.get("news") if isinstance(nodes, dict) else None
    if isinstance(news_node, dict):
        news_result = news_node.get("result")
        if isinstance(news_result, dict) and isinstance(news_result.get("news"), dict):
            news = news_result["news"]
        else:
            news = {
                "status": "unavailable" if news_node.get("status") in {"failed", "unavailable"} else "empty",
                "providers": [],
                "articles": [],
                "sentiment": {
                    "status": "unscored", "score": None, "sample_count": 0,
                    "publisher_count": 0, "confidence": 0.0,
                    "reason": "news graph node returned no structured result",
                },
            }
    else:
        market = "INDIA" if symbol.endswith((".NS", ".BO")) else "US"
        news = fetch_company_news(symbol, company_name, timespan=timespan, market=market)
    point_in_time = _persist_brief_observations(symbol, snapshot, {"filings": node_result("filings")}, news)
    event_result = node_result("events")
    tracked_events = event_result.get("events", []) if isinstance(event_result.get("events"), list) else []
    source_names = {
        "fundamentals": "Company fundamentals",
        "filings": "Regulatory filings",
        "insiders": "Insider activity",
        "earnings": "Earnings",
        "corporate_actions": "Corporate actions",
        "sector": "Sector context",
        "macro": "Macro context",
        "patents": "Innovation and patents",
        "institutional": "Institutional activity",
        "news": "Multi-source news",
        "events": "Tracked event forecasts",
    }
    sources = []
    for key, label in source_names.items():
        node = nodes.get(key, {}) if isinstance(nodes, dict) else {}
        sources.append({
            "name": label,
            "status": node.get("status", "not_selected") if isinstance(node, dict) else "unknown",
            "evidence_count": node.get("evidence_count", 0) if isinstance(node, dict) else 0,
        })
    for provider in news.get("providers", []):
        sources.append({
            "name": provider.get("name", "News provider"),
            "status": provider.get("status", "unknown"),
            "retrieved_at": news.get("retrieved_at"),
        })
    return {
        "ticker": symbol,
        "company": {
            "name": company_name,
            "sector": snapshot.get("sector"),
            "market_cap": snapshot.get("market_cap"),
            "price": snapshot.get("price"),
            "currency": snapshot.get("currency") or ("INR" if symbol.endswith((".NS", ".BO")) else "USD"),
            "as_of": snapshot.get("as_of"),
            "price_as_of": snapshot.get("price_as_of"),
            "retrieved_at": snapshot.get("retrieved_at"),
        },
        "recommendation": decision,
        "fundamentals": snapshot,
        "events": {
            "filings": node_result("filings"),
            "earnings": node_result("earnings"),
            "insiders": node_result("insiders"),
            "corporate_actions": node_result("corporate_actions"),
            "sector": node_result("sector"),
            "macro": node_result("macro"),
            "patents": node_result("patents"),
            "tracked": tracked_events,
            "event_pressure": event_result.get("event_pressure"),
            "event_status": event_result.get("status", "unavailable"),
            "macro_status": node_result("macro").get("status", "unavailable"),
        },
        "news": news,
        "research": {
            "status": decision.get("research_status", "complete"),
            "evidence_yield": run.evidence_yield,
            "duration_ms": run.duration_ms,
            "contradictions": run.contradictions,
        },
        "evidence": {
            "coverage": decision.get("evidence_coverage", 0.0),
            "sources": sources,
        },
        "point_in_time": point_in_time,
        "advisory_only": True,
    }


@app.get("/research/history/{ticker}")
def research_history(ticker: str, as_of: datetime | None = None):
    symbol = ticker.strip().upper()
    if not symbol or len(symbol) > 15 or not symbol[0].isalnum() or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in symbol):
        raise HTTPException(400, "invalid ticker symbol")
    try:
        store = PointInTimeStore(_point_in_time_path())
    except Exception as exc:
        raise HTTPException(503, f"point-in-time store unavailable: {type(exc).__name__}")
    try:
        rows = store.latest(symbol, as_of)
        return {
            "ticker": symbol,
            "as_of": as_of,
            "observation_count": len(rows),
            "observations": [{
                "metric": row.metric, "value": row.value, "source": row.source,
                "source_url": row.source_url, "confidence": row.confidence,
                "available_at": row.available_at, "published_at": row.published_at,
                "observed_at": row.observed_at, "retrieved_at": row.retrieved_at,
                "provider": row.provider, "content_digest": row.content_digest,
                "extraction_version": row.extraction_version,
            } for row in rows],
        }
    except Exception as exc:
        raise HTTPException(503, f"point-in-time history unavailable: {type(exc).__name__}")
    finally:
        store.close()


@app.get("/research/news/{ticker}")
def research_news(ticker: str, timespan: str = "7d", limit: int = 25, market: str | None = None):
    symbol = ticker.strip().upper()
    selected_market = market or ("INDIA" if symbol.endswith((".NS", ".BO")) else "US")
    try:
        return fetch_company_news(symbol, timespan=timespan, limit=limit, market=selected_market)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get("/research/macro")
def research_macro(series_id: str | None = None):
    data = live_macro()
    if series_id:
        data["fred"] = fred_series(series_id)
    return data

@app.get("/research/sector/{sector}")
def research_sector(sector: str):
    return sector_state(sector)

@app.get("/research/institutional/{manager_cik}")
def research_institutional(manager_cik: str, limit: int = 4):
    positions = parse_13f(manager_cik, max(1, min(limit, 8)))
    return summarize_positions(positions)

@app.post("/research/counterfactual/{ticker}")
def research_counterfactual(ticker: str, changes: dict[str, dict[str, float]], budget: int = 3):
    snapshot = snapshot_ticker(ticker.upper())
    selected = fabric.select_branches(list(changes), budget=max(1, min(3, budget)))
    selected_changes = {name: changes[name] for name in selected}
    return {"ticker": ticker.upper(), "selected_branches": selected, "branches": [b.__dict__ for b in evaluate_branches(snapshot, selected_changes)]}

@app.get("/research/monthly-recommendations")
def monthly_recommendations(
    market: str = "US",
    tickers: str | None = None,
    benchmark: str | None = None,
):
    selected = [x.strip() for x in tickers.split(",") if x.strip()] if tickers else None
    try:
        return build_monthly_recommendations(market, selected, benchmark)
    except ValueError as exc:
        raise HTTPException(400, str(exc))




@app.get("/research/macro-intelligence")
def macro_intelligence(market: str = "US"):
    try:
        return macro_state(market)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/research/regime-history")
def regime_history():
    from .regime_intelligence import extreme_event_history, classify_market_regime
    return {"current": classify_market_regime().__dict__, "historical_anchors": extreme_event_history()}


@app.get("/research/events")
def research_events():
    memory = EventMemory(_event_memory_path())
    return {"status": memory.load_status, "error_type": memory.load_error_type, "events": [x.__dict__ for x in memory.events], "calibration": memory.calibration()}


@app.post("/research/events/forecast")
def forecast_event(payload: dict):
    try:
        event = build_forecast(
            payload["category"], payload["entity"], payload["expected_at"],
            int(payload.get("window_days", 1)), float(payload.get("importance", 0.5)),
            float(payload.get("probability", 0.5)), float(payload.get("expected_direction", 0.0)),
            payload.get("source", "user-provided"),
            payload.get("affected_metrics", []), payload.get("thesis_impacts", []),
        )
        memory = EventMemory(_event_memory_path())
        memory.record_forecast(event)
        return event.__dict__
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/research/events/extract")
def extract_events(payload: dict):
    try:
        events = extract_event_candidates(
            str(payload["text"]), str(payload.get("category", "macro")),
            str(payload.get("entity", "market")), str(payload.get("source", "research")),
        )
        memory = EventMemory(_event_memory_path())
        for event in events:
            memory.record_forecast(event)
        return {"events": [x.__dict__ for x in events]}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/research/events/{event_id}/observe")
def observe_event(event_id: str, payload: dict):
    try:
        event = EventMemory(_event_memory_path()).record_observation(
            event_id, str(payload["observed_at"]), float(payload["market_reaction"]),
            float(payload["surprise"]) if payload.get("surprise") is not None else None,
        )
        return event.__dict__
    except KeyError:
        raise HTTPException(404, "event forecast not found")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/research/advance-tax")
def advance_tax_status(year: int | None = None):
    from datetime import datetime
    target = year or datetime.now().year
    memory = AdvanceTaxMemory()
    return {"source_status": official_source_status(), "calendar": tax_calendar(target), "history": memory.history(), "latest": memory.latest()}


@app.post("/research/advance-tax")
def record_advance_tax(payload: dict):
    try:
        signal = from_official_observation(
            str(payload["period"]), payload.get("collection"),
            payload.get("yoy_growth"), payload.get("corporate_growth"),
            payload.get("personal_growth"), payload.get("source", "Income Tax Department"),
        )
        memory = AdvanceTaxMemory()
        memory.record(signal)
        return signal
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))

@app.get("/research/backtest/{ticker}")
def research_backtest(ticker: str):
    import yfinance as yf
    history = yf.Ticker(ticker.upper()).history(period="5y", auto_adjust=True)
    if history.empty: raise HTTPException(404, "no price history available")
    results = walk_forward_strategies(history["Close"])
    return {"ticker": ticker.upper(), "summary": summarize_strategy_walk_forward(results),
            "observations": results.to_dict(orient="records")}

@app.get("/learning/experience")
def learning_experience(): return {"stats": experience.capability_stats()}

@app.post("/learning/experience")
def record_experience(payload: dict):
    row = Experience(**payload)
    experience.record(row)
    return {"recorded": True, "stats": experience.capability_stats()}

@app.get("/learning/policy")
def learning_policy(): return policy.snapshot()

@app.get("/learning/calibration")
def learning_calibration():
    return outcomes.calibration_stats()

@app.get("/learning/outcomes")
def learning_outcomes():
    return {"stats": outcomes.outcome_stats(),
            "pending": [x.__dict__ for x in outcomes.pending()],
            "outcomes": [x.__dict__ for x in outcomes.outcomes[-100:]]}

@app.post("/learning/decision")
def record_decision(payload: dict):
    try:
        episode = DecisionEpisode(**payload)
        outcomes.record_decision(episode)
        return {"recorded": True, "episode_id": episode.id}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))

@app.post("/learning/outcome/{episode_id}/evaluate")
def evaluate_outcome(episode_id: str, benchmark: str | None = "^GSPC"):
    episode=outcomes.get(episode_id)
    if not episode: raise HTTPException(404, "decision episode not found")
    try:
        outcome=evaluate_episode(episode, benchmark=benchmark)
        outcomes.record_outcome(outcome)
        policy.learn_outcome(outcome, episode)
        policy.save()
        return outcome.__dict__
    except Exception as exc:
        raise HTTPException(502, f"outcome evaluation failed: {exc}")

@app.post("/learning/outcomes/evaluate-due")
def evaluate_due_outcomes(benchmark: str | None = "^GSPC"):
    evaluated=[]
    for episode in outcomes.pending():
        try:
            outcome=evaluate_episode(episode, benchmark=benchmark)
            outcomes.record_outcome(outcome)
            policy.learn_outcome(outcome, episode)
            evaluated.append(outcome.__dict__)
        except Exception:
            continue
    if evaluated: policy.save()
    return {"evaluated": len(evaluated), "outcomes": evaluated, "stats": outcomes.outcome_stats()}

@app.get("/learning/plan")
def learning_plan(required_evidence: float = 0.7):
    capabilities=["filings","fundamentals","insiders","earnings","institutional","sector","macro","patents"]
    return fabric.plan(capabilities,max(0,min(1,required_evidence))).__dict__

@app.get("/research/patents/{organization}")
def research_patents(organization: str, limit: int = 25):
    return search_patents(organization, limit)

@app.get("/research/graph/{ticker}")
def research_graph_plan(ticker: str):
    graph = ResearchGraph()
    return ResearchOrchestrator(fabric).plan(graph)

@app.get("/research/run/{ticker}")
def research_run(ticker: str):
    run = ResearchOrchestrator(fabric).run(ticker.upper(), COLLECTORS)
    return run.__dict__
