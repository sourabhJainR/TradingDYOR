"""Cross-repository integration tests against the pinned AUREN delivery modules."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

AUREN_ROOT = Path(os.environ["AUREN_ROOT"]).resolve()
if not (AUREN_ROOT / "portable" / "response_delivery.py").is_file():
    raise RuntimeError("AUREN_ROOT does not point to the pinned AUREN checkout")
sys.path.insert(0, str(AUREN_ROOT))

from portable.progress_journal import ProgressJournal
from portable.response_delivery import (
    ResponseDeliveryError,
    assemble_response,
    chunk_response,
    deliver_response,
)


def research_evidence_bundle() -> str:
    """Build a deterministic, Unicode-rich multi-ticker evidence workload."""
    rows = []
    for ticker in ("NVDA", "MU", "RKLB", "MTSI", "XE", "OKLO", "XYL", "AVGO"):
        rows.append(
            f"## {ticker}\n"
            f"Financials: revenue_growth=0.18; gross_margin=0.62; net_debt=0.4x\n"
            f"News: supplier capacity update; event_type=operations; sentiment_sample=17\n"
            f"Filing: publisher=regulator; published_at=2026-10-30T12:00:00Z; "
            f"retrieved_at=2026-10-31T06:00:00Z; source_digest={'a' * 64}\n"
            f"Thesis: bull=execution improves; base=delivery on plan; bear=capex delay\n"
            f"Risk: stale or conflicting evidence must reduce confidence; "
            f"missing data must remain unavailable. Unicode: ₹ € — 東京\n"
            + ("LongUnbrokenEvidenceToken_" + ticker + "_" + "x" * 180) + "\n"
        )
    return "\n".join(rows) * 9


class IdempotentResearchReceiver:
    """Receiver-owned durable acceptance keyed by response/index/chunk digest."""

    def __init__(self):
        self.accepted = {}
        self.lose_first_ack = True

    def __call__(self, chunk, idempotency_key):
        existing = self.accepted.get(idempotency_key)
        if existing is None:
            self.accepted[idempotency_key] = chunk
            if self.lose_first_ack:
                self.lose_first_ack = False
                raise TimeoutError("simulated disconnect after durable receiver acceptance")
        else:
            if existing != chunk:
                raise AssertionError("idempotency key reused for different chunk content")
        return {
            "response_id": chunk.response_id,
            "index": chunk.index,
            "sha256": chunk.sha256,
        }


class AurenRuntimeDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal_path = Path(self.temp.name) / "progress.jsonl"
        self.task_id = "TradingDYOR:multi-ticker-research:delivery-test"

    def tearDown(self):
        self.temp.cleanup()

    def test_large_research_bundle_is_lossless_and_byte_bounded(self):
        source = research_evidence_bundle()
        manifest, chunks = chunk_response(source, max_bytes=512)
        self.assertGreater(len(chunks), 10)
        self.assertTrue(all(chunk.utf8_bytes <= 512 for chunk in chunks))
        self.assertEqual(assemble_response(manifest, chunks), source)
        self.assertEqual(manifest.total_bytes, len(source.encode("utf-8")))

    def test_receiver_accept_then_lost_ack_resumes_idempotently_after_restart(self):
        source = research_evidence_bundle()
        receiver = IdempotentResearchReceiver()
        journal = ProgressJournal(self.journal_path)

        with self.assertRaisesRegex(TimeoutError, "simulated disconnect"):
            deliver_response(
                source, task_id=self.task_id, journal=journal,
                send_chunk=receiver, max_bytes=512,
            )

        before_restart = ProgressJournal(self.journal_path).response_delivery_checkpoint(
            self.task_id, chunk_response(source, max_bytes=512)[0].response_id
        )
        self.assertEqual(before_restart["acknowledged_index"], 0)

        restarted = ProgressJournal(self.journal_path)
        receipt = deliver_response(
            source, task_id=self.task_id, journal=restarted,
            send_chunk=receiver, max_bytes=512,
        )
        manifest, chunks = chunk_response(source, max_bytes=512)
        self.assertTrue(receipt.complete)
        self.assertEqual(receipt.acknowledged_chunks, len(chunks))
        self.assertEqual(
            restarted.response_delivery_checkpoint(self.task_id, manifest.response_id)["acknowledged_index"],
            len(chunks),
        )
        rebuilt = "".join(receiver.accepted[
            f"{manifest.response_id}:{chunk.index}:{chunk.sha256}"
        ].text for chunk in chunks)
        self.assertEqual(rebuilt, source)

    def test_bad_receiver_ack_does_not_advance_durable_cursor(self):
        source = "news\n" + ("evidence-" * 100)
        journal = ProgressJournal(self.journal_path)

        def bad_receiver(chunk, _key):
            return {"response_id": chunk.response_id, "index": chunk.index, "sha256": "0" * 64}

        manifest, _ = chunk_response(source, max_bytes=64)
        with self.assertRaisesRegex(ResponseDeliveryError, "does not match"):
            deliver_response(
                source, task_id=self.task_id, journal=journal,
                send_chunk=bad_receiver, max_bytes=64,
            )
        checkpoint = ProgressJournal(self.journal_path).response_delivery_checkpoint(
            self.task_id, manifest.response_id
        )
        self.assertEqual(checkpoint["acknowledged_index"], 0)

    def test_reordered_or_corrupted_chunks_fail_closed(self):
        source = research_evidence_bundle()
        manifest, chunks = chunk_response(source, max_bytes=512)
        with self.assertRaises(ResponseDeliveryError):
            assemble_response(manifest, tuple(reversed(chunks)))
        changed = list(chunks)
        first = changed[0]
        changed[0] = type(first)(
            response_id=first.response_id, index=first.index, total=first.total,
            text=first.text + "tampered", sha256=first.sha256,
        )
        with self.assertRaisesRegex(ResponseDeliveryError, "digest mismatch"):
            assemble_response(manifest, changed)

    def test_cancellation_leaves_only_confirmed_cursor(self):
        source = research_evidence_bundle()
        journal = ProgressJournal(self.journal_path)
        accepted = []

        def receiver(chunk, _key):
            accepted.append(chunk)
            return {
                "response_id": chunk.response_id,
                "index": chunk.index,
                "sha256": chunk.sha256,
            }

        calls = {"count": 0}
        def cancel_after_one():
            calls["count"] += 1
            return calls["count"] > 1

        with self.assertRaisesRegex(ResponseDeliveryError, "cancelled"):
            deliver_response(
                source, task_id=self.task_id, journal=journal,
                send_chunk=receiver, max_bytes=512, cancelled=cancel_after_one,
            )
        manifest, chunks = chunk_response(source, max_bytes=512)
        checkpoint = ProgressJournal(self.journal_path).response_delivery_checkpoint(
            self.task_id, manifest.response_id
        )
        self.assertEqual(checkpoint["acknowledged_index"], 1)
        self.assertEqual(len(accepted), 1)
        self.assertGreater(len(chunks), 1)

    def test_expired_deadline_sends_no_chunk_and_advances_no_cursor(self):
        source = research_evidence_bundle()
        journal = ProgressJournal(self.journal_path)
        sent = []

        def receiver(chunk, _key):
            sent.append(chunk)
            return {
                "response_id": chunk.response_id,
                "index": chunk.index,
                "sha256": chunk.sha256,
            }

        manifest, _ = chunk_response(source, max_bytes=512)
        with self.assertRaisesRegex(TimeoutError, "deadline expired"):
            deliver_response(
                source, task_id=self.task_id, journal=journal,
                send_chunk=receiver, max_bytes=512, deadline=time.monotonic() - 1,
            )
        checkpoint = ProgressJournal(self.journal_path).response_delivery_checkpoint(
            self.task_id, manifest.response_id
        )
        self.assertEqual(sent, [])
        self.assertEqual(checkpoint["acknowledged_index"], 0)


if __name__ == "__main__":
    unittest.main()
