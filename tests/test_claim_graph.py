from tradingdyor.claim_graph import ClaimGraph


def test_claim_graph_provenance_and_resolution():
    graph=ClaimGraph()
    graph.add_claim("guidance", "up", "SEC", "https://sec.example", "2026-09-25", "2026-09-25", 0.9, 0.9)
    graph.add_claim("guidance", "flat", "Aggregator", "https://agg.example", "2026-09-25", "2026-09-25", 0.9, 0.9)
    result=graph.snapshot()
    assert result["evidence"]["count"] == 2
    assert result["reconciled"][0]["value"] == "up"
    assert result["reconciled"][0]["status"] == "resolved-primary"


def test_primary_tier_conflict_stays_contested():
    graph=ClaimGraph()
    graph.add_claim("guidance", "up", "SEC", confidence=0.9)
    graph.add_claim("guidance", "flat", "SEC", confidence=0.8)
    assert graph.reconcile()[0]["status"] == "contested"
