from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

AUREN_ROOT = Path(os.environ["AUREN_ROOT"]).resolve()
if not (AUREN_ROOT / "portable" / "dashboard_server.py").is_file():
    raise RuntimeError("AUREN_ROOT does not point to the pinned AUREN checkout")
sys.path.insert(0, str(AUREN_ROOT))

from portable import dashboard_server
from portable.agency_release_lifecycle import ArtifactStore
from portable.hybrid_model_router import HybridModelRouter
from portable.progress_journal import ProgressJournal
from portable.response_delivery_artifacts import ResponseArtifactRepository


def stock_brief_fixture():
    tickers = ("NVDA", "MU", "RKLB", "MTSI", "AVGO", "OKLO", "XYL", "XE")
    return {
        "schema_version": "tradingdyor-stock-brief-v1",
        "market": "US",
        "as_of": "2026-10-31T09:00:00Z",
        "universe": {"source": "exchange-directory-fixture", "retrieved_at": "2026-10-31T08:55:00Z",
                     "point_in_time_archive": False, "tickers": list(tickers)},
        "companies": [{
            "ticker": ticker,
            "fundamentals": {
                "revenue_growth": {"value": 0.18, "period": "FY", "published_at": None},
                "gross_margin": {"value": 0.62, "period": "FY", "published_at": None},
                "debt_to_equity": {"value": 0.4, "period": "FY", "published_at": None},
            },
            "news": [{
                "headline": f"{ticker} supplier capacity and demand update {n}",
                "publisher": f"Publisher-{n % 5}",
                "url": f"https://example.invalid/{ticker}/{n}",
                "published_at": None if n % 4 == 0 else "2026-10-30T12:00:00Z",
                "seen_at": "2026-10-31T07:00:00Z",
                "retrieved_at": "2026-10-31T08:00:00Z",
                "sentiment": "unscored", "event_type": "operations",
                "source_digest": hashlib.sha256(f"{ticker}:{n}".encode()).hexdigest(),
            } for n in range(45)],
            "events": [{
                "event_id": f"{ticker}-event-{n}",
                "category": ("company", "macro", "geopolitical")[n % 3],
                "forecast_at": "2026-11-05T14:00:00Z", "observed_at": None, "status": "forecast",
            } for n in range(6)],
            "scenarios": {
                "bull": {"thesis": "execution improves", "confidence": 0.58},
                "base": {"thesis": "delivery stays on plan", "confidence": 0.46},
                "bear": {"thesis": "capex or schedule slips", "confidence": 0.31},
            },
            "evidence_coverage": {
                "selected_sources": 50, "completed_sources": 37, "partial": True,
                "missing_metrics_do_not_pass_filters": True,
            },
        } for ticker in tickers],
        "decision_policy": {
            "no_lookahead": True, "next_session_entry": True,
            "future_or_retrieval_only_evidence_excluded": True, "trade_execution_supported": False,
        },
    }


class AurenDashboardHostTestBed(TestCase):
    def _server(self, root):
        runtime = root / ".auren"
        store = ArtifactStore(runtime / "releases")
        handler = type("TradingDYORHostTestHandler", (dashboard_server._Handler,), {
            "artifact_store": store,
            "response_repository": ResponseArtifactRepository(store),
            "progress_journal": ProgressJournal(runtime / "progress.jsonl"),
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    @staticmethod
    def _request(server, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw, status = response.read(), response.status
        response_headers = dict(response.getheaders())
        connection.close()
        return status, response_headers, json.loads(raw.decode("utf-8")) if raw else None

    @staticmethod
    def _stop(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    def test_stock_brief_survives_lost_ack_and_dashboard_restart(self):
        brief = stock_brief_fixture()
        routed = SimpleNamespace(
            provider="fixture", model="tradingdyor-testbed", success=True, attempts=1,
            latency_ms=2.0, resource_usage={"fixture_bytes": 0}, fallback_reason=None,
            result={"stock_brief": brief}, error=None,
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(
            HybridModelRouter, "route", return_value=routed,
        ):
            root = Path(directory)
            receiver = root / "receiver"
            receiver.mkdir()
            server, thread = self._server(root)
            try:
                status, headers, manifest = self._request(
                    server, "POST", "/api/route", {"task": "deliver multi-ticker stock brief"},
                    {"Accept": dashboard_server.CHUNKED_RESPONSE_ACCEPT},
                )
                self.assertEqual(status, 202)
                self.assertEqual(headers["X-AUREN-Delivery-Mode"], "chunked-pull-v1")
                self.assertGreater(manifest["total_chunks"], 1)

                status, _, first = self._request(server, "GET", manifest["next"])
                self.assertEqual(status, 200)
                (receiver / "00000001.utf8").write_bytes(first["text"].encode("utf-8"))
                ack = {
                    "chunk_index": 1, "chunk_sha256": first["chunk_sha256"],
                    "response_sha256": manifest["response_sha256"],
                    "total_chunks": manifest["total_chunks"],
                }
                status, _, _lost_ack_response = self._request(server, "POST", manifest["ack"], ack)
                self.assertEqual(status, 200)
            finally:
                self._stop(server, thread)

            # Receiver has chunk 1 on disk but lost the acknowledgement response.
            server, thread = self._server(root)
            try:
                status, _, checkpoint = self._request(server, "GET", manifest["status"])
                self.assertEqual(status, 200)
                self.assertEqual(checkpoint["acknowledged_index"], 1)
                self.assertFalse(checkpoint["complete"])

                while True:
                    status, _, chunk = self._request(server, "GET", manifest["next"])
                    self.assertEqual(status, 200)
                    if chunk.get("all_chunks_acknowledged"):
                        break
                    self.assertEqual(chunk["chunk_index"], len(list(receiver.glob("*.utf8"))) + 1)
                    (receiver / f"{chunk['chunk_index']:08d}.utf8").write_bytes(
                        chunk["text"].encode("utf-8")
                    )
                    ack = {
                        "chunk_index": chunk["chunk_index"], "chunk_sha256": chunk["chunk_sha256"],
                        "response_sha256": manifest["response_sha256"],
                        "total_chunks": manifest["total_chunks"],
                    }
                    status, _, receipt = self._request(server, "POST", manifest["ack"], ack)
                    self.assertEqual(status, 200)
                    self.assertEqual(receipt["acknowledged_index"], chunk["chunk_index"])

                assembled = "".join(
                    (receiver / f"{i:08d}.utf8").read_text(encoding="utf-8")
                    for i in range(1, manifest["total_chunks"] + 1)
                )
                self.assertEqual(hashlib.sha256(assembled.encode("utf-8")).hexdigest(), manifest["response_sha256"])
                decoded = json.loads(assembled)
                self.assertEqual(decoded["result"]["stock_brief"], brief)
                self.assertTrue(decoded["result"]["stock_brief"]["decision_policy"]["no_lookahead"])

                status, _, pre_complete = self._request(server, "GET", manifest["status"])
                self.assertEqual(status, 200)
                self.assertTrue(pre_complete["all_chunks_acknowledged"])
                self.assertFalse(pre_complete["complete"])

                status, _, receipt = self._request(server, "POST", manifest["complete"], {
                    "response_sha256": manifest["response_sha256"],
                    "total_chunks": manifest["total_chunks"],
                })
                self.assertEqual(status, 200)
                self.assertTrue(receipt["completed"])
                status, _, final = self._request(server, "GET", manifest["status"])
                self.assertEqual(status, 200)
                self.assertTrue(final["complete"])
            finally:
                self._stop(server, thread)


if __name__ == "__main__":
    import unittest
    unittest.main()
