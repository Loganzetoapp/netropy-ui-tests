"""Run with: pytest --confcutdir=webapp webapp/tests/test_runner.py -v
The real pytest subprocess call is replaced with a fake so this suite
runs in milliseconds with no browser, no box, and no real test
execution.
"""
import json
import time

import pytest

from webapp.runner import AlreadyRunningError, TestRunner, _find_test_result


def _fake_subprocess_run_factory(history_dir, outcome="pass", stored_suffix=""):
    """`stored_suffix` simulates the browser-parametrize suffix real
    pytest-playwright always appends to the recorded nodeid (e.g.
    "[chromium]") even though the *triggering* nodeid built by catalog.py
    never has one. Default "" preserves the old (unrealistic) behavior of
    writing back the triggering nodeid verbatim, for tests that don't
    care about the suffix mismatch."""

    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        batch_id = env["NETROPY_WEBAPP_BATCH_ID"]
        # cmd = [sys.executable, "-m", "pytest", nodeid, "-m", marker]
        nodeid = cmd[3] + stored_suffix
        history_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"{time.time_ns()}"
        (history_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "git_sha": "abc123",
                    "git_branch": "main",
                    "markers": "hardware_free",
                    "duration": 1.23,
                    "batch_id": batch_id,
                    "tests": [
                        {
                            "nodeid": nodeid,
                            "outcome": outcome,
                            "duration": 1.23,
                            "failure_message": None if outcome == "pass" else "boom",
                            "screenshot": None,
                            "trace": None,
                        }
                    ],
                }
            )
        )

        class _Result:
            returncode = 0 if outcome == "pass" else 1

        return _Result()

    return _fake_run


def test_single_passing_run(tmp_path):
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "pass"),
    )
    batch_id = runner.start(
        "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login", "hardware_free", 1
    )
    events = list(runner.events(batch_id))
    assert [type(e).__name__ for e in events] == [
        "IterationEvent",
        "IterationEvent",
        "BatchCompleteEvent",
    ]
    assert events[0].status == "running"
    assert events[1].status == "passed"
    assert events[2].passed == 1
    assert events[2].total == 1


def test_failing_run_reports_failure_message(tmp_path):
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "fail"),
    )
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "failed"
    assert events[1].detail == "boom"


def test_second_run_rejected_while_one_is_active(tmp_path):
    history_dir = tmp_path / "history"

    def _slow_fake_run(cmd, cwd, env, capture_output, text, timeout):
        time.sleep(0.2)
        return _fake_subprocess_run_factory(history_dir, "pass")(
            cmd, cwd, env, capture_output, text, timeout
        )

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_slow_fake_run)
    runner.start("tests/x.py::test_x", "hardware_free", 1)
    with pytest.raises(AlreadyRunningError):
        runner.start("tests/y.py::test_y", "hardware_free", 1)


def test_repeat_count_runs_all_iterations_even_after_failure(tmp_path):
    history_dir = tmp_path / "history"
    calls = {"n": 0}
    real_fake = _fake_subprocess_run_factory(history_dir, "fail")

    def _counting_fake(*args, **kwargs):
        calls["n"] += 1
        return real_fake(*args, **kwargs)

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_counting_fake)
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 3)
    list(runner.events(batch_id))
    assert calls["n"] == 3


# --- Regression coverage for the [chromium]-suffix nodeid-matching bug ---
#
# Real pytest-playwright always records the executed nodeid WITH a
# "[chromium]" browser-parametrize suffix, but catalog.py builds the
# triggering nodeid WITHOUT one. The old exact-match `_find_test_result`
# never matched, so every webapp-triggered run reported
# "error: No result recorded for this run" regardless of actual outcome.
# The tests above never caught this because their fake subprocess wrote
# the triggering nodeid back verbatim (stored_suffix="") — these tests
# use stored_suffix="[chromium]" to reproduce the real mismatch.


def test_single_passing_run_matches_chromium_suffixed_nodeid(tmp_path):
    """The triggering nodeid has no suffix; the history file records it
    with "[chromium]" appended, exactly as real pytest-playwright does.
    Before the fix this always fell through to "error"."""
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(
            history_dir, "pass", stored_suffix="[chromium]"
        ),
    )
    batch_id = runner.start(
        "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login", "hardware_free", 1
    )
    events = list(runner.events(batch_id))
    assert events[1].status == "passed"
    assert events[1].detail is None
    assert events[2].passed == 1


def test_failing_run_matches_chromium_suffixed_nodeid_with_failure_message(tmp_path):
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(
            history_dir, "fail", stored_suffix="[chromium]"
        ),
    )
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "failed"
    assert events[1].detail == "boom"


def test_find_test_result_exact_match_still_works(tmp_path):
    """A nodeid recorded with no suffix at all (e.g. a hypothetical
    non-parametrized future test, or another browser-engine config) must
    still match exactly."""
    history_file = tmp_path / "run.json"
    history_file.write_text(
        json.dumps(
            {
                "tests": [
                    {"nodeid": "tests/x.py::test_x", "outcome": "pass"},
                ]
            }
        )
    )
    result = _find_test_result(history_file, "tests/x.py::test_x")
    assert result is not None
    assert result["outcome"] == "pass"


def test_find_test_result_matches_bracketed_suffix(tmp_path):
    history_file = tmp_path / "run.json"
    history_file.write_text(
        json.dumps(
            {
                "tests": [
                    {"nodeid": "tests/x.py::test_x[chromium]", "outcome": "pass"},
                ]
            }
        )
    )
    result = _find_test_result(history_file, "tests/x.py::test_x")
    assert result is not None
    assert result["outcome"] == "pass"


def test_find_test_result_does_not_false_match_longer_nodeid_prefix(tmp_path):
    """A nodeid that is a plain string-prefix of another test's nodeid,
    but not immediately followed by "[", must not match — e.g.
    "test_bar" is a prefix of "test_bar_extra[chromium]" but they are
    different tests."""
    history_file = tmp_path / "run.json"
    history_file.write_text(
        json.dumps(
            {
                "tests": [
                    {"nodeid": "tests/foo.py::test_bar_extra[chromium]", "outcome": "pass"},
                ]
            }
        )
    )
    result = _find_test_result(history_file, "tests/foo.py::test_bar")
    assert result is None


def test_find_test_result_matches_real_history_nodeid_shape(tmp_path):
    """Hermetic proof against a real recorded shape: this exact nodeid
    (triggering nodeid vs. stored nodeid) was copied from an actual
    results/history/*.json entry produced by a real pytest-playwright run
    in this repo, not synthesized — see
    results/history/20260910T181043Z.json."""
    history_file = tmp_path / "run.json"
    real_stored_nodeid = (
        "tests/t10_t12_lifecycle/test_t10_t12_lifecycle_arp_10mbps_64b.py"
        "::test_t10_t12_lifecycle_arp_10mbps_64b[chromium]"
    )
    triggering_nodeid = (
        "tests/t10_t12_lifecycle/test_t10_t12_lifecycle_arp_10mbps_64b.py"
        "::test_t10_t12_lifecycle_arp_10mbps_64b"
    )
    history_file.write_text(
        json.dumps({"tests": [{"nodeid": real_stored_nodeid, "outcome": "pass"}]})
    )
    result = _find_test_result(history_file, triggering_nodeid)
    assert result is not None
    assert result["outcome"] == "pass"
