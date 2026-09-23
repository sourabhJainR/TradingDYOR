from tradingdyor.decision_fabric import DecisionFabric
from tradingdyor.experience import Experience, ExperienceMemory


def test_fabric_plan_selects_evidence():
    f=DecisionFabric()
    p=f.plan(["filings","fundamentals","insiders","macro"])
    assert len(p.capabilities)>=2 and p.verification_depth>=0.7


def test_history_changes_routing_and_depth(tmp_path):
    memory=ExperienceMemory(tmp_path / "experience.json")
    for _ in range(3):
        memory.record(Experience("filings", True, 10, 0.95, 1.5, 0, 0.9))
        memory.record(Experience("macro", False, 300, 0.1, 2.5, 2, 0.1))
    fabric=DecisionFabric(memory=memory)
    plan=fabric.plan(["filings","macro"], required_evidence=0.7)
    assert plan.capabilities[0] == "filings"
    assert plan.verification_depth >= 1.5
    assert plan.retry_budget >= 1


def test_cold_start_memory_does_not_override_policy(tmp_path):
    memory=ExperienceMemory(tmp_path / "experience.json")
    memory.record(Experience("macro", False, 10, 0.0, 3.0, 3, 0.0))
    assert memory.recommend(["macro","filings"]) == ""


def test_branch_selection_uses_experience(tmp_path):
    memory=ExperienceMemory(tmp_path / "experience.json")
    for _ in range(2):
        memory.record(Experience("bull", True, 20, 0.9, 1.0, 0, 1.5))
        memory.record(Experience("bear", True, 20, 0.4, 1.0, 0, 0.2))
    fabric=DecisionFabric(memory=memory)
    assert fabric.select_branches(["bull","bear"], budget=1) == ["bull"]
