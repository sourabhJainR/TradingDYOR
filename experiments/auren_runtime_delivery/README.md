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

The workflow checks out AUREN at exact main commit `19a6dfe7a884f2cf7732ab8cedbd272ccf73246b`. The tests import the actual `portable.dashboard_server`, `portable.response_delivery_artifacts`, `portable.response_delivery`, and `portable.progress_journal` modules directly from that checkout. The pin is intentionally immutable so a test run can be reproduced.

## Run

```bash
AUREN_ROOT=/path/to/AUREN python -m unittest discover -s experiments/auren_runtime_delivery -p 'runtime_*_contract.py' -v
```

The host test persists receiver chunks before acknowledgement, simulates a lost ack response and dashboard process restart, verifies the resumed research brief digest, and requires a separate final completion receipt.

## Current coverage boundary

This test bed proves the dashboard HTTP receiver-acknowledgement path only. It does not prove universal host integration. CLI stdout/file delivery remains an atomic sink contract; MCP stdio remains bounded and fail-closed for protocol frames rather than using response chunking; supervisor-parent completion must still be verified against a real host-owned acknowledgement. These are tracked under AUREN issue #1140.

The suite is a repository CI contract, not an operator staging rehearsal or an independent production-host isolation audit. The pinned AUREN revision is a test target, not a runtime dependency of TradingDYOR.
