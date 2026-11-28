#!/usr/bin/env python3
"""Poll GitHub Actions browser-QA run status. Read-only; requires GH_TOKEN."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Callable

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW_PREFIX = ".github/workflows/"


def validate_workflow_path(path: str) -> None:
    if (
        not isinstance(path, str)
        or not path.startswith(WORKFLOW_PREFIX)
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("expected workflow path must be a safe .github/workflows path")


def default_request(url: str, token: str, timeout: float) -> dict:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    if not url.startswith("https://api.github.com/repos/"):
        raise ValueError("polling is restricted to GitHub's HTTPS API host")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=timeout) as response:
        return json.loads(response.read(65536))


def match_workflow_path(observed: object, expected: str) -> tuple[str | None, str | None, bool]:
    if observed == expected:
        return expected, None, True
    prefix = expected + "@"
    if isinstance(observed, str) and observed.startswith(prefix):
        ref = observed[len(prefix):]
        if ref and len(ref) <= 256 and not any(ord(char) < 32 for char in ref):
            return expected, ref, True
    return observed if isinstance(observed, str) else None, None, False


def poll_run(
    repo: str,
    run_id: int,
    expected_sha: str,
    *,
    token: str,
    expected_workflow_path: str = ".github/workflows/browser-qa.yml",
    poll_seconds: int = 15,
    timeout_seconds: int = 900,
    request: Callable[[str, str, float], dict] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    on_update: Callable[[dict], None] | None = None,
) -> dict:
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or any(part in {".", ".."} for part in repo.split("/")):
        raise ValueError("invalid repository slug")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("run_id must be positive")
    if not SHA.fullmatch(expected_sha):
        raise ValueError("expected_sha must be a full commit SHA")
    if not isinstance(token, str) or not token:
        raise ValueError("token is required")
    validate_workflow_path(expected_workflow_path)
    if type(poll_seconds) is not int or poll_seconds < 1:
        raise ValueError("poll_seconds must be a positive integer")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ValueError("timeout_seconds must be a positive integer")

    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    deadline = clock() + timeout_seconds
    fetch = request or default_request
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return {
                "run_id": run_id, "repo": repo, "expected_sha": expected_sha,
                "observed_sha": None, "expected_workflow_path": expected_workflow_path,
                "observed_workflow_path": None, "status": None, "conclusion": None,
                "url": None, "state": "timeout",
            }
        try:
            run = fetch(url, token, min(20.0, remaining))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            state = "timeout" if clock() >= deadline else "blocked"
            return {
                "run_id": run_id, "repo": repo, "expected_sha": expected_sha,
                "observed_sha": None, "expected_workflow_path": expected_workflow_path,
                "observed_workflow_path": None, "status": None, "conclusion": None,
                "url": None, "transport_error": type(exc).__name__, "state": state,
            }

        raw_workflow_path = run.get("path")
        normalized_path, workflow_ref, workflow_matches = match_workflow_path(
            raw_workflow_path, expected_workflow_path
        )
        result = {
            "run_id": run_id, "repo": repo, "expected_sha": expected_sha,
            "observed_sha": run.get("head_sha"),
            "expected_workflow_path": expected_workflow_path,
            "observed_workflow_path": normalized_path,
            "raw_observed_workflow_path": raw_workflow_path,
            "observed_workflow_ref": workflow_ref,
            "workflow_id": run.get("workflow_id"), "workflow_name": run.get("name"),
            "status": run.get("status"), "conclusion": run.get("conclusion"),
            "url": run.get("html_url"),
        }
        if not workflow_matches:
            result["state"] = "workflow_mismatch"
            return result
        if result["observed_sha"] != expected_sha:
            result["state"] = "mismatch"
            return result
        if run.get("status") == "completed":
            result["state"] = "passed" if run.get("conclusion") == "success" else "failed"
            return result
        remaining = deadline - clock()
        if remaining <= 0:
            result["state"] = "timeout"
            return result
        if on_update is not None:
            on_update(result)
        sleep(min(poll_seconds, remaining))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="sourabhJainR/TradingDYOR")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-workflow-path", default=".github/workflows/browser-qa.yml")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN is required")
    result = poll_run(
        args.repo, args.run_id, args.expected_sha, token=token,
        expected_workflow_path=args.expected_workflow_path,
        poll_seconds=args.poll_seconds, timeout_seconds=args.timeout_seconds,
        on_update=lambda value: print(json.dumps(value), flush=True),
    )
    print(json.dumps(result))
    return {"passed": 0, "failed": 1, "mismatch": 2, "timeout": 3,
            "workflow_mismatch": 4, "blocked": 5}.get(result["state"], 5)


if __name__ == "__main__":
    raise SystemExit(main())
