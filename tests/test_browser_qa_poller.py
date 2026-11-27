import importlib.util
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "scripts" / "poll_browser_qa.py"
spec = importlib.util.spec_from_file_location("poll_browser_qa", module_path)
if spec is None or spec.loader is None:
    raise ImportError("unable to load browser QA poller")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
poll_run = module.poll_run

SHA = "a" * 40
PATH = ".github/workflows/browser-qa.yml"


def run_data(**updates):
    return {
        "head_sha": SHA, "path": PATH, "workflow_id": 1, "name": "Browser QA",
        "status": "completed", "conclusion": "success",
        "html_url": "https://github.com/owner/repo/actions/runs/1",
        **updates,
    }


def test_pass_requires_exact_sha_and_workflow_path():
    result = poll_run("owner/repo", 1, SHA, token="fake", request=lambda u, t, timeout: run_data())
    assert result["state"] == "passed"


def test_workflow_path_mismatch_not_pass():
    result = poll_run(
        "owner/repo", 1, SHA, token="fake",
        request=lambda u, t, timeout: run_data(path=".github/workflows/test.yml"),
    )
    assert result["state"] == "workflow_mismatch"


def test_sha_mismatch_not_pass():
    result = poll_run("owner/repo", 1, SHA, token="fake", request=lambda u, t, timeout: run_data(head_sha="b" * 40))
    assert result["state"] == "mismatch"


def test_completed_failure_not_pass():
    result = poll_run("owner/repo", 1, SHA, token="fake", request=lambda u, t, timeout: run_data(conclusion="failure"))
    assert result["state"] == "failed"


def test_request_timeout_is_capped_by_remaining_budget():
    observed = []
    result = poll_run(
        "owner/repo", 1, SHA, token="fake", timeout_seconds=1, clock=lambda: 0,
        request=lambda u, t, timeout: (observed.append(timeout) or run_data()),
    )
    assert observed == [1]
    assert result["state"] == "passed"


def test_running_run_times_out_without_unbounded_sleep():
    calls = [0]
    request_calls = [0]

    def clock():
        calls[0] += 1
        return 0 if calls[0] <= 2 else 2

    def request(url, token, timeout):
        request_calls[0] += 1
        return run_data(status="in_progress", conclusion=None)

    result = poll_run(
        "owner/repo", 1, SHA, token="fake", timeout_seconds=1,
        request=request, clock=clock, sleep=lambda _: None,
    )
    assert request_calls[0] == 1
    assert result["state"] == "timeout"


def test_transport_error_is_blocked():
    result = poll_run(
        "owner/repo", 1, SHA, token="fake",
        request=lambda u, t, timeout: (_ for _ in ()).throw(TimeoutError()),
        clock=lambda: 0, sleep=lambda _: None,
    )
    assert result["state"] == "blocked"
