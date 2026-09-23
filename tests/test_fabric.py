from tradingdyor.decision_fabric import DecisionFabric
def test_fabric_plan_selects_evidence():
    f=DecisionFabric()
    p=f.plan(["filings","fundamentals","insiders","macro"])
    assert len(p.capabilities)>=2 and p.verification_depth>=0.7
