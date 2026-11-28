# Ardisa compiler/runtime acceptance test bed

This isolated TradingDYOR experiment checks the real Ardisa compiler and native runtime against deterministic application-domain fixtures. It is not a production dependency and does not alter TradingDYOR research, market-data, portfolio, or recommendation behavior.

## What it verifies

- A real `.ardisa` source file executes through the Ardisa native CLI.
- Repeated bootstrap compilation emits byte-identical ARDISA-EXEC-V1 artifacts.
- The emitted artifact verifies and executes with the expected deterministic result.
- Malformed artifacts are rejected.
- Proof/Trace declarations that do not have supported native source operations remain fail-closed and do not emit an artifact.
- Console and native HTTP hosts return the same result from a shared synthetic source fixture.
- HTTP query/body forwarding, unknown-route rejection, and the localhost mutation boundary are tested against a bounded loopback server.
- Evidence records the exact immutable Ardisa commit and fixture SHA-256.

## Run locally

From the TradingDYOR repository root, with a separate Ardisa checkout:

```bash
ARDISA_ROOT=/path/to/Ardisa \
ARDISA_REVISION=310a7dcb3d0968b4b7a5cb5764b038e075bfbf73 \
python -m unittest discover -s experiments/ardisa_compiler -p 'runtime_*_contract.py' -v
```

The dedicated GitHub Actions workflow checks out Ardisa at the immutable candidate revision `310a7dcb3d0968b4b7a5cb5764b038e075bfbf73` from Ardisa PR #417, verifies the checkout SHA, then runs the full Ardisa workspace tests and this suite. The acceptance run starts a loopback-only native HTTP server, calls the real CLI, and shuts it down. The candidate revision is a test target, not a runtime dependency. This pin tests the exact PR #417 candidate and is intentionally not a floating branch reference. Refresh it after the candidate changes or merges before accepting a subsequent test-bed change.

## Boundaries

Fixtures are synthetic and deterministic. No live market data, provider API, broker, credentials, database, or TradingDYOR production module is used. The committed fixtures are not secret or independently held-out corpora. A pass proves only these compiler/runtime and host contracts on the pinned revision; it does not prove complete language support, cryptographic trust, OS isolation, formal verification, desktop/browser lifecycle parity, or self-hosting. Proof/Trace remain fail-closed where source-level native operations are unsupported. Never use this experiment as a trading recommendation or decision signal.
