from tradingdyor.contradictions import detect_contradictions
from tradingdyor.decision_fabric import DecisionFabric
from tradingdyor.research_graph import ResearchGraph, ResearchTask
from tradingdyor.models import SecuritySnapshot
from types import SimpleNamespace
from tradingdyor.orchestrator import ResearchOrchestrator


def test_graph_dependencies():
    graph = ResearchGraph()
    ready = {n.task.id for n in graph.ready()}
    assert "fundamentals" in ready
    assert "synthesis" not in ready


def test_contradiction_prefers_primary_tier():
    rows = [
        {"claim": "revenue guidance", "value": "up", "source": "SEC"},
        {"claim": "revenue guidance", "value": "flat", "source": "Aggregator"},
    ]
    result = detect_contradictions(rows)
    assert result and result[0].severity == "medium"
    assert result[0].sources[0] == "SEC"


def test_orchestrator_parallel_loop_and_learning(tmp_path):
    from tradingdyor.experience import ExperienceMemory
    memory = ExperienceMemory(tmp_path / "experience.json")
    fabric = DecisionFabric(memory=memory)
    calls = []

    def collector(ticker):
        calls.append(ticker)
        return {"evidence_count": 2, "claims": [{"claim": "quality", "value": "high", "source": "SEC"}]}

    graph = ResearchGraph(tasks=(
        ResearchGraph().nodes["fundamentals"].task,
        ResearchGraph().nodes["filings"].task,
    ))
    result = ResearchOrchestrator(fabric, max_workers=2).run("ABC", {"fundamentals": collector, "filings": collector}, graph)
    assert result.graph["completed"] == 2
    assert len(calls) == 2
    assert memory.capability_stats()["fundamentals"]["observations"] == 1.0


def test_orchestrator_synthesizes_partial_results_after_provider_failure():
    class Memory:
        def record(self, _experience):
            return None

    class NoRetryFabric:
        memory = Memory()

        def plan(self, capabilities, required_evidence=0.7):
            return SimpleNamespace(
                capabilities=tuple(capabilities),
                retry_budget=0,
                verification_depth=0.5,
            )

    tasks = (
        ResearchTask("fundamentals", "fundamentals", "Collect company fundamentals"),
        ResearchTask("filings", "filings", "Collect regulatory filings"),
        ResearchTask(
            "synthesis", "synthesis", "Synthesize partial evidence",
            depends_on=("fundamentals", "filings"),
        ),
    )
    graph = ResearchGraph(tasks=tasks)
    snapshot = SecuritySnapshot(
        ticker="ABC", price=10.0, revenue_growth=0.5, earnings_growth=0.4,
        roe=0.2, pe=20.0, debt_to_equity=0.2, momentum_12m=0.3,
        volatility_90d=0.2, evidence_coverage=1.0,
    )

    def fundamentals(_ticker):
        return {
            "evidence_count": 2,
            "snapshot": snapshot.model_dump(mode="json"),
            "claims": [{"claim": "revenue growth", "value": "0.5", "source": "SEC"}],
        }

    def failed_filings(_ticker):
        raise TimeoutError("synthetic provider timeout")

    result = ResearchOrchestrator(NoRetryFabric(), max_workers=2).run(
        "ABC", {"fundamentals": fundamentals, "filings": failed_filings}, graph,
    )

    synthesis = result.graph["nodes"]["synthesis"]
    assert synthesis["status"] == "completed"
    assert synthesis["result"]["status"] == "partial"
    assert synthesis["result"]["missing_tasks"][0]["task_id"] == "filings"
    assert result.decision["research_status"] == "partial"
    assert result.decision["missing_research_tasks"][0]["task_id"] == "filings"
    assert result.decision["evidence_coverage"] <= 0.5
    assert result.decision["confidence"] <= 0.5


def test_missing_collector_is_unavailable_not_successful_evidence():
    class Memory:
        def record(self, _experience):
            return None

    class NoRetryFabric:
        memory = Memory()

        def plan(self, capabilities, required_evidence=0.7):
            return SimpleNamespace(
                capabilities=tuple(capabilities),
                retry_budget=0,
                verification_depth=0.5,
            )

    tasks = (
        ResearchTask("fundamentals", "fundamentals", "Collect company fundamentals"),
        ResearchTask("institutional", "institutional", "Collect institutional activity"),
        ResearchTask(
            "synthesis", "synthesis", "Synthesize partial evidence",
            depends_on=("fundamentals", "institutional"),
        ),
    )
    graph = ResearchGraph(tasks=tasks)
    snapshot = SecuritySnapshot(ticker="ABC", price=None, evidence_coverage=0.5)

    def fundamentals(_ticker):
        return {"evidence_count": 1, "snapshot": snapshot.model_dump(mode="json"),
                "claims": [{"claim": "company", "value": "ABC", "source": "Market data"}]}

    result = ResearchOrchestrator(NoRetryFabric(), max_workers=1).run(
        "ABC", {"fundamentals": fundamentals}, graph,
    )

    assert result.graph["nodes"]["institutional"]["status"] == "unavailable"
    assert result.graph["nodes"]["synthesis"]["status"] == "completed"
    assert result.graph["nodes"]["synthesis"]["result"]["status"] == "partial"
    assert result.graph["nodes"]["synthesis"]["result"]["missing_tasks"][0]["status"] == "unavailable"
