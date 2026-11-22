# Ardisa compiler/runtime acceptance test bed

This isolated TradingDYOR experiment checks the real Ardisa compiler and native
runtime against a separate application-domain fixture. It is not a production
dependency and does not alter TradingDYOR research, market-data, portfolio, or
recommendation behavior.

## What it verifies

- A real `.ardisa` source file executes through the Ardisa native CLI.
- Repeated bootstrap compilation emits byte-identical ARDISA-EXEC-V1 artifacts.
- The emitted artifact verifies and executes with the expected deterministic result.
- Malformed artifacts are rejected.
- Proof/Trace declarations that do not have supported native source operations
  remain fail-closed and do not emit an artifact.
- Evidence records the exact immutable Ardisa commit and fixture SHA-256.

## Run locally

From the TradingDYOR repository root, with a separate Ardisa checkout:

```bash
ARDISA_ROOT=/path/to/Ardisa \
ARDISA_REVISION=<40-character-commit-sha> \
python -m unittest discover -s experiments/ardisa_compiler -p 'test_*.py' -v
```

The dedicated GitHub Actions workflow checks out the candidate Ardisa commit `2d9dfd5fbfbaf9ea6d0a89b2433fdbfaba2f4bf5` from PR #399, verifies the checkout SHA,
then runs the full Ardisa workspace tests and this suite. The pinned PR also
includes the loopback-only native HTTP host, exact listener Host validation,
and loopback-only browser Origin checks. DNS-rebinding and remote-origin negative
tests run in the workspace suite. The test invokes `cargo run -p ardisa` against that checkout;
it does not reimplement or simulate the compiler. After PR #399 merges, refresh
this pin to the merge commit before merging the test-bed change.

## Boundaries

Fixtures are synthetic and deterministic. No live market data, provider API,
broker, credentials, database, or TradingDYOR production module is used. The
committed fixture is not a secret or independently held-out corpus. A pass
proves only these CLI/runtime contracts on the pinned revision; it does not
prove complete language support, cryptographic trust, OS isolation, formal
verification, or self-hosting. Proof/Trace remain fail-closed where source-level
native operations are unsupported. Never use this experiment as a trading
recommendation or decision signal.
