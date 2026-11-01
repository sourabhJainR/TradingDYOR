# AUREN runtime delivery test bed

This experiment runs the real AUREN response-delivery primitives and host adapters against a deterministic one-page stock-research workload. It is not a copied implementation and does not use live market data.

## Contract under test

- Lossless UTF-8 chunking of large, multi-source research evidence over the dashboard HTTP transport.
- Exact response and per-chunk digest validation.
- Receiver-owned idempotency for a chunk accepted before its acknowledgement is lost.
- Resume from the last journaled acknowledgement after process reconstruction.
- No cursor advancement for missing, malformed, reordered, or corrupted acknowledgements.
- Bounded chunk size, explicit cancellation/deadline behavior, and final completion only after receiver acknowledgement.
- Real CLI subprocess delivery to stdout and files, including Unicode byte preservation, digest receipts, oversize rejection without partial output, and refusal to overwrite without explicit permission.

The test workload represents a multi-ticker research batch with filings, news, event classifications, sentiment samples, financial metrics, and source provenance. Values are deterministic fixtures, not market facts or recommendations.

## Pinned AUREN source

The workflow checks out AUREN at exact main commit `19a6dfe7a884f2cf7732ab8cedbd272ccf73246b`. The tests import the actual `portable.dashboard_server`, `portable.response_delivery_artifacts`, `portable.response_delivery`, `portable.progress_journal`, and CLI delivery entry point directly from that checkout. The pin is immutable so a test run can be reproduced.

## Run

```bash
AUREN_ROOT=/path/to/AUREN python -m unittest discover -s experiments/auren_runtime_delivery -p 'runtime_*_contract.py' -v
```

The HTTP host test persists receiver chunks before acknowledgement, simulates a lost ack response and dashboard process restart, verifies the resumed research brief digest, and requires a separate final completion receipt. The CLI subprocess tests verify exact stdout bytes and SHA-256 receipts, reject oversized output before writing, and preserve existing files when overwrite is not explicitly enabled.

## Current coverage boundary

The dashboard HTTP route is the current resumable chunked transport. CLI stdout/file delivery remains atomic by design; it does not claim resumable chunking. MCP stdio retains bounded, fail-closed protocol frames and must not split a protocol frame into response chunks. This suite does not prove every provider/tool host path, an independent production isolation audit, or an operator staging rehearsal. Remaining cross-host integration work is tracked under AUREN issue #1140.

The pinned AUREN revision is a test target, not a runtime dependency of TradingDYOR.
