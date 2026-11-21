"""Cross-repository acceptance tests for the pinned Ardisa compiler/runtime.

The tests compile and execute real .ardisa source through the checked-out Ardisa
CLI. They use only deterministic synthetic fixtures and never import TradingDYOR
production modules or access market data, providers, brokers, or credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
ARDISA_ROOT = Path(os.environ["ARDISA_ROOT"]).resolve()
REVISION = os.environ["ARDISA_REVISION"]

if not (AARDISA_ROOT / "Cargo.toml").is_file():
    raise RuntimeError("ARDISA_ROOT must point to the pinned Ardisa checkout")


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "cargo", "run", "--quiet", "--manifest-path",
            str(AARDISA_ROOT / "Cargo.toml"), "-p", "ardisa", "--", *map(str, args),
        ],
        cwd=AARDISA_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=900,
    )


class ArdisaCompilerAcceptance(unittest.TestCase):
    def test_real_source_runs_through_native_runtime(self) -> None:
        source = ROOT / "fixtures" / "hello.ardisa"
        result = cli("run", str(source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("42", result.stdout.strip())

    def test_bootstrap_artifact_is_deterministic_and_executable(self) -> None:
        source = ROOT / "fixtures" / "hello.ardisa"
        with tempfile.TemporaryDirectory(prefix="ardisa-testbed-") as directory:
            first = Path(directory) / "first.aexe"
            second = Path(directory) / "second.aexe"
            for output in (first, second):
                result = cli("bootstrap", "compile", str(source), str(output))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(output.is_file())
                verify = cli("bootstrap", "verify", str(output))
                self.assertEqual(0, verify.returncode, verify.stderr)
            first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
            self.assertEqual(first_bytes, second_bytes, "repeat builds must be byte-identical")
            self.assertEqual(
                hashlib.sha256(first_bytes).hexdigest(),
                hashlib.sha256(second_bytes).hexdigest(),
            )
            executed = cli("bootstrap", "run", str(first))
            self.assertEqual(0, executed.returncode, executed.stderr)
            self.assertEqual("42", executed.stdout.strip())

    def test_malformed_native_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ardisa-testbed-") as directory:
            malformed = Path(directory) / "malformed.aexe"
            malformed.write_bytes(b"not-an-ardisa-executable")
            result = cli("bootstrap", "verify", str(malformed))
            self.assertNotEqual(0, result.returncode, "invalid artifacts must fail closed")

    def test_proof_trace_declarations_without_native_operations_fail_closed(self) -> None:
        source = ROOT / "fixtures" / "unsupported_proof_trace.ardisa"
        with tempfile.TemporaryDirectory(prefix="ardisa-testbed-") as directory:
            output = Path(directory) / "must-not-exist.aexe"
            result = cli("bootstrap", "compile", str(source), str(output))
            self.assertNotEqual(
                0, result.returncode,
                "unsupported Proof/Trace source operations must not be silently accepted",
            )
            self.assertFalse(output.exists(), "failed compilation must not emit an artifact")

    def test_evidence_is_bound_to_the_requested_immutable_revision(self) -> None:
        self.assertRegex(REVISION, r"^[0-9a-f]{40}$")
        source = ROOT / "fixtures" / "hello.ardisa"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        evidence = {
            "contract": "ardisa-compiler-acceptance-v1",
            "ardisa_revision": REVISION,
            "fixture": source.relative_to(ROOT).as_posix(),
            "fixture_sha256": digest,
            "network_access_required": False,
            "production_trading_code_changed": False,
        }
        self.assertEqual("ardisa-compiler-acceptance-v1", evidence["contract"])
        self.assertEqual(64, len(evidence["fixture_sha256"]))
        print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
