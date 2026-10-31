from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .claim_graph import ClaimGraph
from .contradictions import detect_contradictions
from .decision import decide
from .decision_fabric import DecisionFabric
from .experience import Experience
from .models import SecuritySnapshot
from .outcome_learning import DecisionEpisode, OutcomeMemory, stable_episode_id
from .research_graph import ResearchGraph

Collector = Callable[[str], dict]

@dataclass(frozen=True)
class ResearchRun:
    ticker: str
    graph: dict
    provenance: dict
    contradictions: list[dict]
    decision: dict | None
    evidence_yield: float
    duration_ms: float
    outcome_episode_id: str | None = None

class ResearchOrchestrator:
    def __init__(self, fabric: DecisionFabric | None = None, max_workers: int = 4,
                 outcome_memory: OutcomeMemory | None = None):
        self.fabric = fabric or DecisionFabric()
        self.max_workers = max(1, max_workers)
        self.outcomes = outcome_memory or OutcomeMemory()

    def plan(self, graph: ResearchGraph) -> dict:
        capabilities = [n.task.capability for n in graph.nodes.values() if n.task.id != "synthesis"]
        plan = self.fabric.plan(capabilities, required_evidence=0.7)
        selected = set(plan.capabilities)
        available = {node.task.capability for node in graph.nodes.values() if node.task.id != "synthesis"}
        selected.update({"fundamentals", "news", "macro", "events"} & available)
        for node in graph.nodes.values():
            if node.task.id == "synthesis":
                node.task = type(node.task)(
                    node.task.id, node.task.capability, node.task.description,
                    tuple(sorted(selected)), node.task.expected_evidence_yield,
                    node.task.verification_required, node.task.cost,
                )
            elif node.task.capability not in selected:
                node.status = "skipped"
        return {"fabric": plan.__dict__, "graph": graph.snapshot()}

    def _synthesize(self, ticker: str, graph: ResearchGraph) -> dict:
        claims, evidence_count, snapshot = [], 0, None
        for node in graph.nodes.values():
            if node.result:
                evidence_count += node.evidence_count
                claims.extend(node.result.get("claims", []))
                if node.task.id == "fundamentals" and node.result.get("snapshot"):
                    snapshot = node.result["snapshot"]
        source_nodes = [n for n in graph.nodes.values() if n.task.id != "synthesis"]
        completed_nodes = [n for n in source_nodes if n.status == "completed"]
        missing_nodes = [
            {"task_id": n.task.id, "status": (n.result.get("status") if isinstance(n.result, dict) and n.result.get("status") in {"partial", "empty", "unavailable"} else n.status), "error": n.error}
            for n in source_nodes
            if n.status in {"failed", "unavailable", "pending", "running"}
            or (isinstance(n.result, dict) and n.result.get("status") in {"partial", "empty", "unavailable"})
        ]
        skipped_nodes = [
            {"task_id": n.task.id, "status": n.status}
            for n in source_nodes if n.status == "skipped"
        ]
        return {
            "ticker": ticker,
            "evidence_count": evidence_count,
            "claims": claims,
            "snapshot": snapshot,
            "source_tasks": [n.task.id for n in completed_nodes],
            "missing_tasks": missing_nodes,
            "skipped_tasks": skipped_nodes,
            "status": "partial" if missing_nodes else "complete",
        }

    def run(self, ticker: str, collectors: dict[str, Collector], graph: ResearchGraph | None = None) -> ResearchRun:
        graph = graph or ResearchGraph()
        started = perf_counter()
        plan = self.plan(graph)
        attempts = {k: 0 for k in graph.nodes}
        while True:
            ready = graph.ready()
            if not ready: break
            synthesis = [n for n in ready if n.task.id == "synthesis"]
            if synthesis:
                node=synthesis[0]; graph.start(node.task.id)
                result=self._synthesize(ticker, graph); graph.complete(node.task.id,result,result["evidence_count"]); continue
            ready=[n for n in ready if n.task.capability in collectors]
            for node in graph.ready():
                if node.task.capability not in collectors:
                    graph.unavailable(node.task.id, "collector_not_configured")
            if not ready: continue
            with ThreadPoolExecutor(max_workers=min(self.max_workers,len(ready))) as pool:
                futures={}
                for node in ready:
                    graph.start(node.task.id)
                    futures[pool.submit(collectors[node.task.capability],ticker)]=node
                for future in as_completed(futures):
                    node=futures[future]; attempts[node.task.id]+=1
                    try:
                        result=future.result()
                        result=result if isinstance(result,dict) else {"value":result}
                        evidence_count=int(result.get("evidence_count",0))
                        if result.get("status") == "unavailable":
                            graph.unavailable(
                                node.task.id,
                                str(result.get("reason") or "collector_unavailable"),
                                result,
                                evidence_count,
                            )
                            self.fabric.memory.record(Experience(
                                node.task.capability, False, (perf_counter()-started)*1000,
                                0.0, node.task.verification_required, attempts[node.task.id]-1, 0.0,
                            ))
                        else:
                            graph.complete(node.task.id,result,evidence_count)
                            quality = min(1.0,evidence_count/5.0)
                            if result.get("status") in {"partial", "empty"}:
                                quality = 0.0 if result.get("status") == "empty" else quality * 0.5
                            self.fabric.memory.record(Experience(
                                node.task.capability, True, (perf_counter()-started)*1000,
                                quality, node.task.verification_required, attempts[node.task.id]-1,
                                node.task.expected_evidence_yield,
                            ))
                    except Exception as exc:
                        retry_budget=self.fabric.plan([node.task.capability]).retry_budget
                        if attempts[node.task.id] <= retry_budget: graph.nodes[node.task.id].status="pending"
                        else:
                            graph.fail(node.task.id,str(exc))
                            self.fabric.memory.record(Experience(node.task.capability,False,(perf_counter()-started)*1000,
                                0.0,node.task.verification_required,attempts[node.task.id]-1,0.0))

        claims=[]; snapshot_data=None
        for node in graph.nodes.values():
            if node.result and isinstance(node.result.get("claims"),list): claims.extend(node.result["claims"])
            if node.task.id=="synthesis" and node.result: snapshot_data=node.result.get("snapshot")
        provenance_graph=ClaimGraph()
        for claim in claims:
            provenance_graph.add_claim(text=str(claim.get("claim","")),value=claim.get("value",""),
                source=str(claim.get("source","Unknown")),url=str(claim.get("url","")),
                observed_at=claim.get("observed_at"),available_at=claim.get("available_at",""),
                confidence=float(claim.get("confidence",0.7)),relevance=float(claim.get("relevance",0.7)))
        provenance=provenance_graph.snapshot()
        contradictions=[c.__dict__ for c in detect_contradictions(claims)]
        decision=None; episode_id=None
        if snapshot_data:
            try:
                snapshot_data = dict(snapshot_data)
                news_node = graph.nodes.get("news")
                news_result = news_node.result if news_node and isinstance(news_node.result, dict) else {}
                sentiment = news_result.get("sentiment", {})
                if isinstance(sentiment, dict):
                    snapshot_data["news_sentiment_status"] = sentiment.get("status", "unscored")
                    snapshot_data["news_sentiment_score"] = sentiment.get("score")
                    snapshot_data["news_sentiment_confidence"] = float(sentiment.get("confidence") or 0.0)
                    snapshot_data["news_sample_count"] = int(sentiment.get("sample_count") or 0)
                    snapshot_data["news_publisher_count"] = int(sentiment.get("publisher_count") or 0)

                macro_node = graph.nodes.get("macro")
                macro_result = macro_node.result if macro_node and isinstance(macro_node.result, dict) else {}
                macro_status = macro_result.get("status", "unavailable")
                snapshot_data["macro_status"] = macro_status
                macro_data = macro_result.get("macro", {})
                regime = macro_data.get("regime", {}) if isinstance(macro_data, dict) else {}
                if macro_status == "available" and isinstance(regime, dict):
                    snapshot_data["market_regime"] = regime.get("name")
                    snapshot_data["regime_score"] = regime.get("score")
                    snapshot_data["regime_stress"] = regime.get("stress")
                    snapshot_data["macro_pressure"] = macro_result.get("macro_pressure")
                else:
                    snapshot_data["market_regime"] = "unknown"
                    snapshot_data["regime_score"] = None
                    snapshot_data["regime_stress"] = None
                    snapshot_data["macro_pressure"] = None

                events_node = graph.nodes.get("events")
                events_result = events_node.result if events_node and isinstance(events_node.result, dict) else {}
                event_status = events_result.get("status", "unavailable")
                snapshot_data["event_status"] = event_status
                snapshot_data["event_pressure"] = (
                    events_result.get("event_pressure")
                    if event_status == "available" else None
                )

                snapshot=SecuritySnapshot.model_validate(snapshot_data)
                decision_model=decide(snapshot,evidence_coverage=provenance["evidence"]["coverage"],provenance=provenance)
                decision=decision_model.model_dump(mode="json")
                synthesis_result = graph.nodes.get("synthesis").result if graph.nodes.get("synthesis") else None
                if isinstance(synthesis_result, dict):
                    source_total = max(1, len([n for n in graph.nodes.values() if n.task.id != "synthesis" and n.status != "skipped"]))
                    source_completed = len([
                        n for n in graph.nodes.values()
                        if n.task.id != "synthesis" and n.status == "completed"
                        and not (isinstance(n.result, dict) and n.result.get("status") in {"partial", "empty", "unavailable"})
                    ])
                    completeness = min(1.0, source_completed / source_total)
                    decision["evidence_coverage"] = min(float(decision.get("evidence_coverage", 0.0)), completeness)
                    decision["confidence"] = min(float(decision.get("confidence", 0.0)), completeness)
                    if completeness < 0.40:
                        decision["action"] = "HOLD"
                        decision["thesis"] = "HOLD thesis: selected research coverage is incomplete."
                    decision["research_status"] = synthesis_result.get("status", "unknown")
                    decision["missing_research_tasks"] = synthesis_result.get("missing_tasks", [])
                if snapshot.price and decision_model.action in {"BUY","SELL","HOLD"}:
                    capabilities=tuple(sorted({n.task.capability for n in graph.nodes.values() if n.status=="completed" and n.task.id!="synthesis"}))
                    sources=tuple(sorted({str(c.get("source","Unknown")) for c in claims if c.get("source")}))
                    episode_id=stable_episode_id(ticker,decision_model.as_of.isoformat())
                    self.outcomes.record_decision(DecisionEpisode(
                        id=episode_id,ticker=ticker.upper(),decision_at=decision_model.as_of.isoformat(),
                        action=decision_model.action,entry_price=float(snapshot.price),thesis=decision_model.thesis,
                        score=decision_model.score,confidence=decision_model.confidence,horizon_days=30,
                        strategy_scores=decision_model.strategy_scores,sources=sources,capabilities=capabilities,
                        verification_depth=float(plan["fabric"]["verification_depth"])))
            except Exception as exc:
                decision={"status":"unavailable","reason":f"decision_synthesis_failed: {exc}"}
        duration_ms=(perf_counter()-started)*1000
        evidence_count=sum(n.evidence_count for n in graph.nodes.values())
        completed=max(1,len([n for n in graph.nodes.values() if n.status=="completed" and n.task.id!="synthesis"]))
        evidence_yield=min(1.0,evidence_count/(completed*5.0))
        return ResearchRun(ticker,graph.snapshot(),provenance,contradictions,decision,evidence_yield,duration_ms,episode_id)
