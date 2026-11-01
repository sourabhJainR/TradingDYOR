# AUREN runtime delivery test bed

This experiment runs the real AUREN response-delivery primitives and dashboard HTTP host against a deterministic one-page stock-research workload. It is not a copied implementation and does not use live market data.

## Contract under test

- Lossless UTF-8 chunking of large, multi-source research evidence.
- Exact response and per-chunk digest validation.
- Receiver-owned idempotency for a chunk accepted before its acknowledgement is lost.
- Resume from the last journaled acknowledgement after process reconstruction.
- No cursor advancement for missing, malformed, reordered, or corrupted acknowledgements.
- Bounded chunk size, explicit cancellation/deadline behavior, and final completion only after receiver acknowledgement.

The test workload represents a multi-ticker research batch with filings, news, event classifications, sentiment samples, financial metrics, and source provenance. Values are deterministic fixtures, not market facts or recommendations.

## Pinned AUREN source

The workflow checks out AUREN at verified main commit `80e6ce1907f32d4304659eff8a0a805cfa6aeb15`, which includes merged delivery, supervisor and durable task-intent work through PR #1179. The tests import the actual `portable.dashboard_server`, `portable.response_delivery_artifacts`, `portable.response_delivery`, and `portable.progress_journal` modules directly from that checkout.

## Run

```bash
AUREN_ROOT=/path/to/AUREN python -m unittest discover -s experiments/auren_runtime_delivery -p 'runtime_*_contract.py' -v
```

The host test persists receiver chunks before acknowledgement, simulates a lost ack response and dashboard process restart, verifies the resumed research brief digest, and requires a separate final completion receipt. It validates the dashboard HTTP path only; MCP stdio remains atomic and supervisor-parent completion/CLI delivery remain open under AUREN issue #1140.

## Production acceptance coverage

The dedicated GitHub Actions workflow pins AUREN at `80e6ce1907f32d4304659eff8a0a805cfa6aeb15` and runs its trusted plan dispatch, durable approvals, supervisor-to-graph/crew cancellation, graph worker lifecycle, state migration, CEO/CTO organization-gate, Docker Arena isolation and receiver-acknowledged HTTP delivery tests. These are repository CI contracts, not an operator staging rehearsal or an independent production-host isolation audit.
