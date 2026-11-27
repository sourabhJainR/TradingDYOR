"""Loopback-only acceptance of Ardisa console and HTTP host parity."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent
ARDISA_ROOT = Path(os.environ["ARDISA_ROOT"]).resolve()
REVISION = os.environ["ARDISA_REVISION"]
SOURCE = ROOT / "fixtures" / "shared_host_parity.ardisa"
SHA = re.compile(r"^[0-9a-f]{40}$")
LISTENING = re.compile(r"listening on http://127\\.0\\.0\\.1:(\\d+)")


def checked_out_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ARDISA_ROOT, text=True,
        capture_output=True, check=False, timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"could not resolve Ardisa revision: {result.stderr}")
    return result.stdout.strip()


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["cargo", "run", "--quiet", "--manifest-path", str(ARDISA_ROOT / "Cargo.toml"),
         "-p", "ardisa", "--", *map(str, args)],
        cwd=ARDISA_ROOT, text=True, capture_output=True, check=False, timeout=900,
    )


def http_request(port: int, method: str, path: str, *, body: str | None = None,
                 headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


class ArdisaApplicationHostAcceptance(unittest.TestCase):
    def test_console_http_parity_and_fail_closed_mutations(self) -> None:
        self.assertRegex(REVISION, SHA)
        self.assertEqual(REVISION, checked_out_revision())

        console = cli("run", str(SOURCE))
        self.assertEqual(0, console.returncode, console.stderr)
        console_value = console.stdout.strip()
        self.assertEqual("shared-result", console_value)

        command = [
            "cargo", "run", "--quiet", "--manifest-path", str(ARDISA_ROOT / "Cargo.toml"),
            "-p", "ardisa", "--", "serve", str(SOURCE), "--allow-http-listen",
            "127.0.0.1:0", "GET", "/", "home", "GET", "/query", "echo_query",
            "POST", "/body", "echo_body",
        ]
        process = subprocess.Popen(
            command, cwd=ARDISA_ROOT, text=True, bufsize=1,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        output: queue.Queue[str | None] = queue.Queue()

        def drain() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output.put(line)
            output.put(None)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        lines: list[str] = []
        port: int | None = None
        deadline = time.monotonic() + 900
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None and output.empty():
                    self.fail("Ardisa server exited before readiness: " + "".join(lines))
                try:
                    line = output.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if line is None:
                    if process.poll() is not None:
                        self.fail("Ardisa server exited before readiness: " + "".join(lines))
                    continue
                lines.append(line)
                match = LISTENING.search(line)
                if match:
                    port = int(match.group(1))
                    break
            self.assertIsNotNone(port, "server readiness timed out: " + "".join(lines))
            assert port is not None
            origin = f"http://127.0.0.1:{port}"

            status, body = http_request(port, "GET", "/")
            self.assertEqual(200, status)
            self.assertEqual(console_value.encode(), body)

            status, body = http_request(port, "GET", "/query?sample=synthetic")
            self.assertEqual(200, status)
            self.assertEqual(b"sample=synthetic", body)

            status, body = http_request(
                port, "POST", "/body", body="synthetic-body", headers={"Origin": origin},
            )
            self.assertEqual(200, status)
            self.assertEqual(b"synthetic-body", body)

            status, _ = http_request(port, "POST", "/body", body="must-reject")
            self.assertEqual(400, status, "mutation without Origin or Fetch Metadata must reject")

            status, _ = http_request(
                port, "POST", "/body", body="wrong-origin",
                headers={"Origin": "http://localhost:3000"},
            )
            self.assertEqual(400, status, "a different origin must reject")

            status, _ = http_request(
                port, "POST", "/body", body="same-site",
                headers={"Sec-Fetch-Site": "same-site"},
            )
            self.assertEqual(400, status, "same-site cross-origin metadata must reject")

            status, _ = http_request(port, "GET", "/missing")
            self.assertEqual(404, status)

            print(json.dumps({
                "contract": "ardisa-application-host-parity-v1",
                "ardisa_revision": checked_out_revision(),
                "fixture_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "console_result": console_value,
                "http_get_result": "shared-result",
                "query_forwarding": "sample=synthetic",
                "body_forwarding": "synthetic-body",
                "csrf_negative_cases": ["missing_origin_and_fetch_metadata", "wrong_origin", "same_site"],
                "unknown_route_status": 404,
                "network_access": "loopback_only",
                "self_hosting_claim": "not_asserted",
            }, sort_keys=True))
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
