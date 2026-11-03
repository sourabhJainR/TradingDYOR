"""Run the real TradingDYOR brief API behind AUREN's canonical plan runtime.

The research providers are deterministic fixtures. This verifies application
composition and runtime authority; it does not claim live provider coverage.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

AUREN_ROOT = Path(os.environ["AUREN_ROOT"]).resolve()
if not (AUREN_ROOT / "portable" / "trusted_plan_dispatch.py").is_file():
    raise RuntimeError("AUREN_ROOT does not point to the pinned AUREN checkout")
sys.path.insert(0, str(AUREN_ROOT))

from portable.agent_org_runtime import authorize_agent_assignment
from portable.durable_approval import DurableApprovalStore
from portable.runtime_recovery import RuntimeExecutionGuard
from portable.trusted_plan_dispatch import TrustedPlanDispatchRoot
from tests.test_engineering_plan_dispatch import prepared

from tradingdyor import api as research_api


_CAPTURED_BRIEFS = []
_HANDLER_ERRORS = []


def stock_research_handler(payload):
    """Importable durable handler registered with the canonical controller."""
    try:
        response = TestClient(research_api.app).get(
            f"/research/brief/{payload['ticker']}"
        )
        if response.status_code != 200:
            raise AssertionError(f"stock brief returned HTTP {response.status_code}: {response.text}")
        brief = response.json()
        _CAPTURED_BRIEFS.append(brief)
        return {
            "ticker": payload["ticker"],
            "http_status": response.status_code,
            "brief_digest": hashlib.sha256(response.content).hexdigest(),
        }
    except Exception as exc:
        _HANDLER_ERRORS.append(repr(exc))
        raise


class StockResearchCanonicalRuntimeTests(unittest.TestCase):
    def test_stock_brief_executes_through_trusted_plan_dispatch(self):
        ticker = "NVDA"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            plan, _run, packet, _review_packet, store, controller, bridge = prepared(temp)
            graph = {
                "nodes": {
                    "fundamentals": {
                        "status": "completed", "evidence_count": 3,
                        "result": {"snapshot": {
                            "ticker": ticker, "company_name": "NVIDIA Corporation",
                            "sector": "Technology", "currency": "USD", "price": 200.0,
                            "market_cap": 3_000_000_000_000,
                            "price_as_of": "2026-11-02T20:00:00+00:00",
                            "retrieved_at": "2026-11-02T20:01:00+00:00",
                        }},
                    },
                    "filings": {"status": "completed", "evidence_count": 1,
                                "result": {"filings": []}},
                    "insiders": {"status": "completed", "evidence_count": 0,
                                 "result": {"buys": 0, "sells": 0}},
                    "earnings": {"status": "completed", "evidence_count": 0,
                                 "result": {"signal": {}}},
                    "corporate_actions": {"status": "completed", "evidence_count": 0,
                                          "result": {"actions": []}},
                }
            }
            decision = {
                "ticker": ticker, "action": "HOLD", "score": 0.1, "confidence": 0.4,
                "evidence_coverage": 0.45, "strategy_agreement": 0.5,
                "thesis": "Evidence is incomplete; wait for stronger confirmation.",
                "key_reasons": ["Fixture coverage is partial"],
                "risks": ["Live provider evidence is not part of this contract test"],
                "invalidation": ["Reassess when fresh evidence is available"],
                "research_status": "partial", "missing_research_tasks": [],
            }
            research_run = SimpleNamespace(
                graph=graph, decision=decision, evidence_yield=0.7,
                duration_ms=25.0, contradictions=[],
            )
            news = {
                "status": "available",
                "retrieved_at": "2026-11-02T20:01:00+00:00",
                "providers": [
                    {"name": "GDELT", "status": "available"},
                    {"name": "Google News RSS", "status": "available"},
                ],
                "articles": [{
                    "story_id": "fixture-story-1",
                    "title": "NVIDIA publishes a quarterly business update",
                    "url": "https://news.example.test/nvda-update",
                    "publisher": "Example News",
                    "publish_time": "2026-11-02T19:30:00+00:00",
                    "seen_at": "2026-11-02T19:35:00+00:00",
                    "source_providers": ["GDELT"],
                }],
                "sentiment": {
                    "status": "unscored", "sample_count": 1, "publisher_count": 1,
                    "methodology": "Insufficient independent publisher coverage",
                },
            }

            _CAPTURED_BRIEFS.clear()
            _HANDLER_ERRORS.clear()

            work_key = "AUREN:TradingDYOR:stock-brief:NVDA:v1"

            def host_assignment_verifier(request):
                return (
                    request.get("role_id") == "BE-01"
                    and request.get("manager_id") == "EM-ENG-01"
                    and request.get("action_class") == "run_scoped_tests"
                    and request.get("scope") == ("NVDA",)
                    and request.get("work_key") == work_key
                    and isinstance(request.get("task_payload_digest"), str)
                    and len(request["task_payload_digest"]) == 64
                )

            controller._agent_assignment_verifier = host_assignment_verifier
            controller.register_handler(
                "stock-research-brief", stock_research_handler,
                execution_class="read_only",
                agent_action_class="run_scoped_tests",
            )
            guard = RuntimeExecutionGuard(max_steps=8, max_attempts=2, deadline_seconds=120)
            admission_digest = guard.snapshot()["digest"]
            assignment_policy = {
                "role_id": "BE-01",
                "manager_id": "EM-ENG-01",
                "action_class": "run_scoped_tests",
                "scope": (ticker,),
            }

            def assignment_resolver(context):
                return authorize_agent_assignment(
                    **assignment_policy,
                    authorizer=host_assignment_verifier,
                    work_key=context["dispatch_key"],
                    task_payload=context["payload"],
                    deadline_seconds=context["deadline_seconds"],
                )

            root = TrustedPlanDispatchRoot(
                controller=controller,
                store=store,
                recovery_bridge=bridge.recovery_bridge,
                approval_store=DurableApprovalStore(controller),
                budget_resolver=lambda _run_id, _task_id, _handler: {
                    "budget_id": "crew:stock-research:acceptance",
                    "guard": guard,
                    "checkpoint_digest": admission_digest,
                    "policy_digest": "a" * 64,
                },
                approval_resolver=lambda _run_id, _task_id, _handler: None,
                assignment_resolver=assignment_resolver,
            )

            payload = {"resource": ticker, "ticker": ticker, "market": "US", "work_key": work_key}
            task = root.dispatch(
                run_id=plan.run_id,
                task_id="implement",
                dispatch_key=work_key,
                handler="stock-research-brief",
                packet=packet,
                payload=payload,
                deadline_seconds=120,
            )

            with (
                patch.dict(os.environ, {"TRADINGDYOR_PIT_DB": str(Path(temp) / "pit.sqlite")}),
                patch.object(
                    research_api, "ResearchOrchestrator",
                    lambda _fabric: SimpleNamespace(run=lambda _ticker, _collectors: research_run),
                ),
                patch.object(research_api, "fetch_company_news", lambda *_args, **_kwargs: news),
            ):
                # Exercise the same trusted preflight explicitly so failures are
                # visible instead of being reduced to a terminal task state.
                controller._verify_engineering_plan_dispatch_checkpoint(task)
                controller._evaluate_guard_for_task(task)
                gates_passed, gate_detail, _gate_evidence = controller._preflight_gates(task)
                self.assertTrue(gates_passed, gate_detail)
                controller.run_once(task.id)

            completed = controller.task(task.id)
            self.assertEqual(
                "completed", completed.state,
                f"handler_errors={_HANDLER_ERRORS!r}; captured_briefs={len(_CAPTURED_BRIEFS)}",
            )
            self.assertEqual(1, len(_CAPTURED_BRIEFS))
            brief = _CAPTURED_BRIEFS[0]
            self.assertEqual(ticker, brief["ticker"])
            self.assertEqual("NVIDIA Corporation", brief["company"]["name"])
            self.assertEqual("HOLD", brief["recommendation"]["action"])
            self.assertEqual("unscored", brief["news"]["sentiment"]["status"])
            self.assertTrue(brief["advisory_only"])
            self.assertEqual(
                "host_authorized_before_submission",
                completed.payload["_auren_agent_assignment"]["authorization"],
            )
            self.assertEqual(
                completed.payload["auren_dispatch"]["assignment_evidence"],
                completed.payload["_auren_agent_assignment"],
            )


if __name__ == "__main__":
    unittest.main()
