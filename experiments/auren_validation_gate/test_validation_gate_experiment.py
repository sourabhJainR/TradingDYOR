"""Regression tests for the AUREN validation-gate experiment."""
import unittest

from run_experiment import (
    build_cases,
    build_manifest,
    candidate_policy,
    evaluate,
    run_negative_controls,
    validate_corpus,
)


class ValidationGateExperimentTests(unittest.TestCase):
    def setUp(self):
        self.manifest = build_manifest()
        self.cases = build_cases()

    def test_manifest_and_corpus_pass_contract_validation(self):
        valid, errors = validate_corpus(self.manifest, self.cases)
        self.assertTrue(valid, errors)

    def test_manifest_digest_tampering_blocks_evaluation(self):
        changed = dict(self.manifest, digest="f" * 64)
        report = evaluate(changed, self.cases)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["promotion_eligible"])

    def test_training_and_holdout_domains_are_disjoint(self):
        changed = dict(self.manifest)
        changed["holdout_domains"] = list(changed["train_domains"])
        # Recompute the digest so the split rule, not just the hash, is exercised.
        from run_experiment import canonical_digest
        changed["digest"] = canonical_digest({
            key: changed[key] for key in (
                "benchmark_id", "version", "train_domains", "holdout_domains", "oracle_ids"
            )
        })
        valid, errors = validate_corpus(changed, self.cases)
        self.assertFalse(valid)
        self.assertTrue(any("overlap" in error for error in errors))

    def test_holdout_transfer_and_training_cases_meet_threshold(self):
        report = evaluate(self.manifest, self.cases)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["promotion_eligible"])
        self.assertEqual(report["holdout_accuracy"], 1.0)
        self.assertEqual(report["train_accuracy"], 1.0)
        self.assertGreater(report["holdout_case_count"], 0)

    def test_negative_controls_all_fail_closed(self):
        controls = run_negative_controls(self.manifest, self.cases)
        self.assertTrue(all(controls.values()), controls)

    def test_future_data_never_produces_buy(self):
        self.assertEqual(candidate_policy({
            "evidence_age_days": 0,
            "evidence_coverage": 1.0,
            "future_data_used": True,
            "source_ids": ["a", "b"],
            "max_evidence_age_days": 10,
        }), "HOLD")

    def test_missing_or_malformed_evidence_fails_closed(self):
        self.assertEqual(candidate_policy({}), "HOLD")
        self.assertEqual(candidate_policy({
            "evidence_age_days": -1,
            "evidence_coverage": 0.9,
            "future_data_used": False,
            "source_ids": ["a", "b"],
            "max_evidence_age_days": 10,
        }), "HOLD")
        self.assertEqual(candidate_policy({
            "evidence_age_days": 1,
            "evidence_coverage": 0.9,
            "future_data_used": False,
            "source_ids": ["a"],
            "max_evidence_age_days": 10,
        }), "HOLD")

    def test_duplicate_case_ids_block_corpus(self):
        duplicated = self.cases + [dict(self.cases[0])]
        valid, errors = validate_corpus(self.manifest, duplicated)
        self.assertFalse(valid)
        self.assertTrue(any("duplicate" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
