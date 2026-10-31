# AUREN runtime delivery test bed

This experiment runs the real AUREN response-delivery and progress-journal modules against a deterministic stock-research workload. It is not a copied implementation and does not use live market data.

## Contract under test

- Lossless UTF-8 chunking of large, multi-source research evidence.
- Exact response and per-chunk digest validation.
- Receiver-owned idempotency for a chunk accepted before its acknowledgement is lost.
- Resume from the last journaled acknowledgement after process reconstruction.
- No cursor advancement for missing, malformed, reordered, or corrupted acknowledgements.
- Bounded chunk size and explicit cancellation/deadline behavior.

The test workload represents a multi-ticker research batch with filings, news, event classifications, sentiment samples, financial metrics, and source provenance. Values are deterministic fixtures, not market facts or recommendations.

## Pinned AUREN source

The workflow checks out AUREN at `0340a56658f0d9d31dc22a32405f88bd792ca9f6`. Update this pin only after reviewing the AUREN revision and its delivery contract. The tests import `portable.response_delivery` and `portable.progress_journal` directly from that checkout.

## Run

```bash
AUREN_ROOT=/path/to/AUREN python -m unittest discover -s experiments/auren_runtime_delivery -p 'test_*.py' -v
```

This is an application-level integration test of reusable AUREN primitives. It does not claim the dashboard browser has a receiver-ack endpoint or that every AUREN host path is integrated. That remains tracked by AUREN issue #1140.
