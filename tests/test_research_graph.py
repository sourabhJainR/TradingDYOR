from tradingdyor.contradictions import detect_contradictions
from tradingdyor.decision_fabric import DecisionFabric
from tradingdyor.research_graph import ResearchGraph
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
