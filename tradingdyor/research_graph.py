from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class ResearchTask:
    id: str
    capability: str
    description: str
    depends_on: tuple[str, ...] = ()
    expected_evidence_yield: float = 0.5
    verification_required: float = 1.0
    cost: float = 1.0


@dataclass
class ResearchNode:
    task: ResearchTask
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    evidence_count: int = 0
    error: str | None = None
    result: dict | None = None


DEFAULT_TASKS = (
    ResearchTask("fundamentals", "fundamentals", "Collect current and historical financial fundamentals", expected_evidence_yield=0.8, cost=1.0),
    ResearchTask("filings", "filings", "Review recent regulatory filings and event signals", expected_evidence_yield=0.9, cost=1.2),
    ResearchTask("insiders", "insiders", "Review recent insider transactions", expected_evidence_yield=0.6, cost=1.0),
    ResearchTask("earnings", "earnings", "Review earnings history and surprises", expected_evidence_yield=0.7, cost=1.0),
    ResearchTask("institutional", "institutional", "Review institutional ownership/flow evidence", expected_evidence_yield=0.5, cost=1.5),
    ResearchTask("sector", "sector", "Assess sector relative strength and regime", expected_evidence_yield=0.7, cost=0.8),
    ResearchTask("macro", "macro", "Assess market and macro regime", expected_evidence_yield=0.6, cost=0.8),
    ResearchTask("patents", "patents", "Assess innovation/patent evidence when configured", expected_evidence_yield=0.4, cost=1.3),
    ResearchTask("synthesis", "synthesis", "Reconcile evidence and produce a research-ready graph", depends_on=("fundamentals", "filings", "insiders", "earnings", "institutional", "sector", "macro", "patents"), expected_evidence_yield=1.0, verification_required=1.5, cost=0.5),
)


class ResearchGraph:
    def __init__(self, tasks: tuple[ResearchTask, ...] = DEFAULT_TASKS):
        self.nodes = {t.id: ResearchNode(t) for t in tasks}

    def ready(self) -> list[ResearchNode]:
        return [
            n for n in self.nodes.values()
            if n.status == "pending" and all(self.nodes[d].status == "completed" for d in n.task.depends_on)
        ]

    def start(self, task_id: str) -> None:
        n = self.nodes[task_id]
        n.status = "running"
        n.started_at = datetime.now(timezone.utc).isoformat()

    def complete(self, task_id: str, result: dict | None = None, evidence_count: int = 0) -> None:
        n = self.nodes[task_id]
        n.status = "completed"
        n.completed_at = datetime.now(timezone.utc).isoformat()
        n.result = result
        n.evidence_count = evidence_count

    def fail(self, task_id: str, error: str) -> None:
        n = self.nodes[task_id]
        n.status = "failed"
        n.completed_at = datetime.now(timezone.utc).isoformat()
        n.error = error

    def snapshot(self) -> dict:
        return {
            "nodes": {
                key: {
                    "capability": n.task.capability,
                    "description": n.task.description,
                    "depends_on": list(n.task.depends_on),
                    "status": n.status,
                    "evidence_count": n.evidence_count,
                    "error": n.error,
                    "result": n.result,
                }
                for key, n in self.nodes.items()
            },
            "completed": sum(n.status == "completed" for n in self.nodes.values()),
            "failed": sum(n.status == "failed" for n in self.nodes.values()),
        }
