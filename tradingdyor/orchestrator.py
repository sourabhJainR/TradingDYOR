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


class ResearchOrchestrator:
    def __init__(self, fabric: DecisionFabric | None = None, max_workers: int = 4):
        self.fabric = fabric or DecisionFabric()
        self.max_workers = max(1, max_workers)

    def plan(self, graph: ResearchGraph) -> dict:
        capabilities = [n.task.capability for n in graph.nodes.values() if n.task.id != "synthesis"]
        plan = self.fabric.plan(capabilities, required_evidence=0.7)
        selected = set(plan.capabilities)
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
        claims: list[dict] = []
        evidence_count = 0
        snapshot = None
        for node in graph.nodes.values():
            if node.result:
                evidence_count += node.evidence_count
                claims.extend(node.result.get("claims", []))
                if node.task.id == "fundamentals" and node.result.get("snapshot"):
                    snapshot = node.result["snapshot"]
        return {
            "ticker": ticker,
            "evidence_count": evidence_count,
            "claims": claims,
            "snapshot": snapshot,
            "source_tasks": [n.task.id for n in graph.nodes.values() if n.status == "completed"],
        }

    def run(self, ticker: str, collectors: dict[str, Collector], graph: ResearchGraph | None = None) -> ResearchRun:
        graph = graph or ResearchGraph()
        started = perf_counter()
        self.plan(graph)
        attempts = {k: 0 for k in graph.nodes}

        while True:
            ready = graph.ready()
            if not ready:
                break
            synthesis = [n for n in ready if n.task.id == "synthesis"]
            if synthesis:
                node = synthesis[0]
                graph.start(node.task.id)
                result = self._synthesize(ticker, graph)
                graph.complete(node.task.id, result, result["evidence_count"])
                continue

            # Every selected branch must have an explicit collector. Missing integrations
            # should be represented as unavailable rather than blocking the DAG.
            ready = [n for n in ready if n.task.capability in collectors]
            for node in graph.ready():
                if node.task.capability not in collectors:
                    graph.complete(node.task.id, {"status": "unavailable", "reason": "collector_not_configured"}, 0)
            if not ready:
                continue

            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready))) as pool:
                futures = {}
                for node in ready:
                    graph.start(node.task.id)
                    futures[pool.submit(collectors[node.task.capability], ticker)] = node
                for future in as_completed(futures):
                    node = futures[future]
                    attempts[node.task.id] += 1
                    try:
                        result = future.result()
                        result = result if isinstance(result, dict) else {"value": result}
                        evidence_count = int(result.get("evidence_count", 0))
                        graph.complete(node.task.id, result, evidence_count)
                        self.fabric.memory.record(Experience(
                            capability=node.task.capability,
                            success=True,
                            duration_ms=(perf_counter() - started) * 1000,
                            evidence_yield=min(1.0, evidence_count / 5.0),
                            verification_depth=node.task.verification_required,
                            retry_count=attempts[node.task.id] - 1,
                            branch_value=node.task.expected_evidence_yield,
                        ))
                    except Exception as exc:
                        retry_budget = self.fabric.plan([node.task.capability]).retry_budget
                        if attempts[node.task.id] <= retry_budget:
                            graph.nodes[node.task.id].status = "pending"
                        else:
                            graph.fail(node.task.id, str(exc))
                            self.fabric.memory.record(Experience(
                                capability=node.task.capability,
                                success=False,
                                duration_ms=(perf_counter() - started) * 1000,
                                evidence_yield=0.0,
                                verification_depth=node.task.verification_required,
                                retry_count=attempts[node.task.id] - 1,
                                branch_value=0.0,
                            ))

        claims: list[dict] = []
        snapshot_data = None
        for node in graph.nodes.values():
            if node.result and isinstance(node.result.get("claims"), list):
                claims.extend(node.result["claims"])
            if node.task.id == "synthesis" and node.result:
                snapshot_data = node.result.get("snapshot")

        provenance_graph = ClaimGraph()
        for claim in claims:
            provenance_graph.add_claim(
                text=str(claim.get("claim", "")), value=claim.get("value", ""),
                source=str(claim.get("source", "Unknown")), url=str(claim.get("url", "")),
                observed_at=claim.get("observed_at"), available_at=claim.get("available_at", ""),
                confidence=float(claim.get("confidence", 0.7)), relevance=float(claim.get("relevance", 0.7)),
            )
        provenance = provenance_graph.snapshot()
        contradictions = [c.__dict__ for c in detect_contradictions(claims)]

        decision = None
        if snapshot_data:
            try:
                snapshot = SecuritySnapshot.model_validate(snapshot_data)
                decision = decide(snapshot, evidence_coverage=provenance["evidence"]["coverage"], provenance=provenance).model_dump(mode="json")
            except Exception as exc:
                decision = {"status": "unavailable", "reason": f"decision_synthesis_failed: {exc}"}

        duration_ms = (perf_counter() - started) * 1000
        evidence_count = sum(n.evidence_count for n in graph.nodes.values())
        completed = max(1, len([n for n in graph.nodes.values() if n.status == "completed" and n.task.id != "synthesis"]))
        evidence_yield = min(1.0, evidence_count / (completed * 5.0))
        return ResearchRun(ticker, graph.snapshot(), provenance, contradictions, decision, evidence_yield, duration_ms)
