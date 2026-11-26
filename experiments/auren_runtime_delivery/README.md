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

Regular TradingDYOR CI and the dedicated test-bed check out AUREN at the
immutable merged-main revision `09955776eefd361cde29a8bf4dc6ab969f690075`. Each checkout verifies the observed
SHA with `git rev-parse HEAD`. The optimizer/rubric and runtime-delivery
contracts use separate checkout directories at the same pin.

The regular CI job runs the optimizer/rubric trust-boundary tests, the core
cross-domain delivery contract, and the dashboard chunked-delivery regression.
The dedicated AUREN test-bed runs supervisor/crew, approval, recovery,
repository execution preflight, live MCP schema preflight, and CLI/sink
acceptance. This adds coverage for the merged plan-bound MCP schema contract
without repeating the core delivery and dashboard chunk tests.

PR #37 was closed without merging; its obsolete overlapping pin is no longer
part of the acceptance plan. The AUREN validation-gate experiment remains
isolated and unchanged.

The tested AUREN pin is immutable and recorded in the workflows. The tests
import the actual `portable.dashboard_server`,
`portable.response_delivery_artifacts`, `portable.response_delivery`,
`portable.progress_journal`, and CLI delivery entry point from that checkout.
The acceptance suite emits JSON evidence containing the observed AUREN SHA and
TradingDYOR test-bed SHA.
## Run

```bash
AUREN_ROOT=/path/to/AUREN \
AUREN_REVISION=<40-character-commit-sha> \
python -m unittest discover -s experiments/auren_runtime_delivery -p 'runtime_*_contract.py' -v
```

The HTTP host test persists receiver chunks before acknowledgement, simulates a lost ack response and dashboard process restart, verifies the resumed research brief digest, and requires a separate final completion receipt. The CLI subprocess tests verify exact stdout bytes and SHA-256 receipts, reject oversized output before writing, and preserve existing files when overwrite is not explicitly enabled.

## Current coverage boundary

The dashboard HTTP route is the current resumable chunked transport. CLI stdout/file delivery remains atomic by design; it does not claim resumable chunking. MCP stdio retains bounded, fail-closed protocol frames and must not split a protocol frame into response chunks. This suite does not prove every provider/tool host path, an independent production isolation audit, or an operator staging rehearsal. Remaining cross-host integration work is tracked under AUREN issue #1140.

The pinned AUREN revision is a test target, not a runtime dependency of TradingDYOR.
