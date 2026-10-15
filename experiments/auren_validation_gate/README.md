# AUREN validation-gate experiment

This is a deterministic, synthetic test bed in TradingDYOR for exercising AUREN's validation-gate contract against a separate application domain. It is deliberately not wired into live investment decisions and uses no live market data.

## What it tests

- Canonical benchmark-manifest digest and corpus digest.
- Disjoint training and holdout domains, unique case IDs, and registered oracle IDs.
- Cross-domain holdout performance for a small evidence-quality decision policy.
- Fail-closed behavior for stale evidence, thin provenance, and future-data/look-ahead leakage.
- Tamper detection and promotion blocking when an integrity or acceptance condition fails.
- Machine-readable evidence output with revision, run time, case-level outcomes, and SHA-256 digests.

## Run locally

```bash
python experiments/auren_validation_gate/run_experiment.py
python -m unittest discover -s experiments/auren_validation_gate -p 'test_*.py' -v
```

The runner writes JSON to stdout and exits non-zero when a gate fails. No network, secrets, brokerage credentials, or production databases are required.

## Boundaries

This is an application-level contract test, not an independent external evaluation campaign. The synthetic holdout is committed in this repository and is therefore not secret or independently custodied. A pass shows the adapter and negative tests behave as expected; it does not prove AUREN's runtime isolation, external generalization, or readiness for promotion. A production promotion still requires AUREN's isolated runner, independently controlled holdout/oracles, and the applicable AUREN gates. Never use this experiment's result as a trading recommendation.
