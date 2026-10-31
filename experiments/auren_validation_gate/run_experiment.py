"""Synthetic cross-domain validation-gate contract test for AUREN.

This is a deterministic application-level experiment. It does not import AUREN
or claim to replace AUREN's isolated, independently custodied Arena.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from typing import Any


BENCHMARK_ID = "tradingdyor-evidence-gate"
BENCHMARK_VERSION = "0.1.0"
ORACLE_ID = "tradingdyor.synthetic-evidence-oracle"
TRAIN_DOMAINS = ("equity-research", "filing-review")
HOLDOUT_DOMAINS = ("macro-regime", "corporate-event")
MIN_HOLDOUT_ACCURACY = 1.0


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest() -> dict[str, Any]:
    train = sorted(set(TRAIN_DOMAINS))
    holdout = sorted(set(HOLDOUT_DOMAINS))
    oracles = [ORACLE_ID]
    if not train or not holdout or set(train) & set(holdout):
        raise ValueError("training and holdout domains must be non-empty and disjoint")
    payload = {
        "benchmark_id": BENCHMARK_ID,
        "version": BENCHMARK_VERSION,
        "train_domains": train,
        "holdout_domains": holdout,
        "oracle_ids": oracles,
    }
    return {**payload, "digest": canonical_digest(payload)}


def build_cases() -> list[dict[str, Any]]:
    # Values are invented solely for deterministic software testing.
    rows = [
        ("train-001", "evidence-quality", "equity-research", False, 2, 0.90, False, ["filing-a", "filing-b"], 7, "BUY"),
        ("train-002", "evidence-quality", "equity-research", False, 18, 0.90, False, ["filing-a", "filing-b"], 7, "HOLD"),
        ("train-003", "provenance", "filing-review", False, 1, 0.40, False, ["filing-a"], 7, "HOLD"),
        ("holdout-001", "transfer", "macro-regime", True, 2, 0.85, False, ["macro-a", "macro-b"], 7, "BUY"),
        ("holdout-002", "transfer", "corporate-event", True, 1, 0.95, True, ["event-a", "event-b"], 7, "HOLD"),
        ("holdout-003", "transfer", "corporate-event", True, 2, 0.55, False, ["event-a", "event-b"], 7, "HOLD"),
    ]
    cases = []
    for cid, kind, domain, holdout, age, coverage, future, sources, max_age, expected in rows:
        cases.append({
            "case_id": cid,
            "kind": kind,
            "domain": domain,
            "holdout": holdout,
            "oracle_id": ORACLE_ID,
            "task": {
                "evidence_age_days": age,
                "evidence_coverage": coverage,
                "future_data_used": future,
                "source_ids": sources,
                "max_evidence_age_days": max_age,
            },
            "expected_action": expected,
        })
    return cases


def validate_corpus(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    payload = {key: manifest.get(key) for key in (
        "benchmark_id", "version", "train_domains", "holdout_domains", "oracle_ids"
    )}
    if manifest.get("digest") != canonical_digest(payload):
        errors.append("manifest digest mismatch")
    train = manifest.get("train_domains")
    holdout = manifest.get("holdout_domains")
    oracles = manifest.get("oracle_ids")
    if not isinstance(train, list) or not train or not all(isinstance(x, str) and x for x in train):
        errors.append("invalid training domains")
        train = []
    if not isinstance(holdout, list) or not holdout or not all(isinstance(x, str) and x for x in holdout):
        errors.append("invalid holdout domains")
        holdout = []
    if set(train) & set(holdout):
        errors.append("training and holdout domains overlap")
    if not isinstance(oracles, list) or not oracles:
        errors.append("oracle registry is empty")
        oracles = []
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case IDs")
    for case in cases:
        domain = case.get("domain")
        is_holdout = case.get("holdout")
        if type(is_holdout) is not bool:
            errors.append(f"invalid holdout flag: {case.get('case_id')}")
        elif is_holdout and domain not in holdout:
            errors.append(f"holdout case outside holdout split: {case.get('case_id')}")
        elif not is_holdout and domain not in train:
            errors.append(f"training case outside training split: {case.get('case_id')}")
        if case.get("oracle_id") not in oracles:
            errors.append(f"unregistered oracle: {case.get('case_id')}")
        if not isinstance(case.get("task"), dict):
            errors.append(f"invalid task payload: {case.get('case_id')}")
    return not errors, errors


def candidate_policy(task: dict[str, Any]) -> str:
    """Fail closed unless evidence is fresh, sufficient, and not look-ahead tainted."""
    try:
        age = task["evidence_age_days"]
        coverage = task["evidence_coverage"]
        future = task["future_data_used"]
        sources = task["source_ids"]
        max_age = task["max_evidence_age_days"]
    except (KeyError, TypeError):
        return "HOLD"
    if type(age) not in (int, float) or age < 0:
        return "HOLD"
    if type(max_age) not in (int, float) or max_age < 0:
        return "HOLD"
    if type(coverage) not in (int, float) or not 0 <= coverage <= 1:
        return "HOLD"
    if type(future) is not bool or future:
        return "HOLD"
    if not isinstance(sources, list) or len(set(s for s in sources if isinstance(s, str))) < 2:
        return "HOLD"
    if age > max_age or coverage < 0.60:
        return "HOLD"
    return "BUY"


def evaluate(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    valid, errors = validate_corpus(manifest, cases)
    corpus_digest = canonical_digest({"manifest": manifest, "cases": cases})
    if not valid:
        return {
            "status": "BLOCKED",
            "promotion_eligible": False,
            "errors": errors,
            "manifest_digest": manifest.get("digest"),
            "corpus_digest": corpus_digest,
            "case_results": [],
        }
    results = []
    for case in cases:
        observed = candidate_policy(case["task"])
        expected = case["expected_action"]
        results.append({
            "case_id": case["case_id"],
            "domain": case["domain"],
            "holdout": case["holdout"],
            "expected": expected,
            "observed": observed,
            "passed": observed == expected,
        })
    holdout_results = [item for item in results if item["holdout"]]
    train_results = [item for item in results if not item["holdout"]]
    holdout_accuracy = (
        sum(item["passed"] for item in holdout_results) / len(holdout_results)
        if holdout_results else 0.0
    )
    train_accuracy = (
        sum(item["passed"] for item in train_results) / len(train_results)
        if train_results else 0.0
    )
    passed = bool(holdout_results) and holdout_accuracy >= MIN_HOLDOUT_ACCURACY and all(
        item["passed"] for item in train_results
    )
    return {
        "status": "PASS" if passed else "BLOCKED",
        "promotion_eligible": passed,
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_version": manifest["version"],
        "manifest_digest": manifest["digest"],
        "corpus_digest": corpus_digest,
        "revision": os.environ.get("GITHUB_SHA", "local-unpinned"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "train_case_count": len(train_results),
        "holdout_case_count": len(holdout_results),
        "train_accuracy": train_accuracy,
        "holdout_accuracy": holdout_accuracy,
        "case_results": results,
        "errors": [],
        "limitations": [
            "Synthetic public holdout; not independently custodied.",
            "Contract-level smoke test; does not execute AUREN's isolated Arena runner.",
            "PASS is not a production promotion or investment recommendation.",
        ],
    }


def run_negative_controls(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, bool]:
    tampered_manifest = dict(manifest)
    tampered_manifest["digest"] = "0" * 64
    integrity_blocked = not validate_corpus(tampered_manifest, cases)[0]

    overlap_manifest = dict(manifest)
    overlap_manifest["holdout_domains"] = list(manifest["train_domains"])
    overlap_manifest["digest"] = canonical_digest({
        key: overlap_manifest[key] for key in (
            "benchmark_id", "version", "train_domains", "holdout_domains", "oracle_ids"
        )
    })
    overlap_blocked = not validate_corpus(overlap_manifest, cases)[0]

    future_task = {
        "evidence_age_days": 1,
        "evidence_coverage": 0.99,
        "future_data_used": True,
        "source_ids": ["source-a", "source-b"],
        "max_evidence_age_days": 7,
    }
    stale_task = {
        "evidence_age_days": 99,
        "evidence_coverage": 0.99,
        "future_data_used": False,
        "source_ids": ["source-a", "source-b"],
        "max_evidence_age_days": 7,
    }
    thin_task = {
        "evidence_age_days": 1,
        "evidence_coverage": 0.99,
        "future_data_used": False,
        "source_ids": ["source-a"],
        "max_evidence_age_days": 7,
    }
    return {
        "manifest_tamper_blocks": integrity_blocked,
        "overlapping_splits_block": overlap_blocked,
        "lookahead_fails_closed": candidate_policy(future_task) == "HOLD",
        "stale_evidence_fails_closed": candidate_policy(stale_task) == "HOLD",
        "thin_provenance_fails_closed": candidate_policy(thin_task) == "HOLD",
    }


def main() -> int:
    manifest = build_manifest()
    cases = build_cases()
    report = evaluate(manifest, cases)
    controls = run_negative_controls(manifest, cases)
    report["negative_controls"] = controls
    controls_pass = all(controls.values())
    report["negative_controls_passed"] = controls_pass
    if not controls_pass:
        report["status"] = "BLOCKED"
        report["promotion_eligible"] = False
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" and controls_pass else 1


if __name__ == "__main__":
    sys.exit(main())
