"""Run with: pytest --confcutdir=webapp webapp/tests/test_runner.py -v
The real pytest subprocess call is replaced with a fake so this suite
runs in milliseconds with no browser, no box, and no real test
execution.
"""
import json
import time

import pytest

from webapp.runner import AlreadyRunningError, TestRunner


def _fake_subprocess_run_factory(history_dir, outcome="pass"):
    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        batch_id = env["NETROPY_WEBAPP_BATCH_ID"]
        # cmd = [sys.executable, "-m", "pytest", nodeid, "-m", marker]
        nodeid = cmd[3]
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
