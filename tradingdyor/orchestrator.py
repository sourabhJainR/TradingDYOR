from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .contradictions import detect_contradictions
from .decision_fabric import DecisionFabric
from .experience import Experience
from .research_graph import ResearchGraph

Collector = Callable[[str], dict]


@dataclass(frozen=True)
class ResearchRun:
    ticker: str
    graph: dict
    contradictions: list[dict]
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
            if node.task.id != "synthesis" and node.task.capability not in selected:
                node.status = "skipped"
        return {"fabric": plan.__dict__, "graph": graph.snapshot()}

    def run(self, ticker: str, collectors: dict[str, Collector], graph: ResearchGraph | None = None) -> ResearchRun:
        graph = graph or ResearchGraph()
        started = perf_counter()
        self.plan(graph)
        attempts = {k: 0 for k in graph.nodes}

        while True:
            ready = [n for n in graph.ready() if n.task.capability in collectors]
            if not ready:
                break
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
                        evidence_count = int(result.get("evidence_count", 0)) if isinstance(result, dict) else 0
                        graph.complete(node.task.id, result if isinstance(result, dict) else {"value": result}, evidence_count)
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
                        if attempts[node.task.id] <= self.fabric.plan([node.task.capability]).retry_budget:
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
        for node in graph.nodes.values():
            if node.result and isinstance(node.result.get("claims"), list):
                claims.extend(node.result["claims"])
        contradictions = [c.__dict__ for c in detect_contradictions(claims)]
        duration_ms = (perf_counter() - started) * 1000
        evidence_count = sum(n.evidence_count for n in graph.nodes.values())
        evidence_yield = min(1.0, evidence_count / max(1, len([n for n in graph.nodes.values() if n.status == "completed"])))
        return ResearchRun(ticker, graph.snapshot(), contradictions, evidence_yield, duration_ms)
