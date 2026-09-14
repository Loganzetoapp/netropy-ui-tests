"""Run with: pytest --confcutdir=webapp webapp/tests/test_runner.py -v
The real pytest subprocess call is replaced with a fake so this suite
runs in milliseconds with no browser, no box, and no real test
execution.
"""
import json
import time

import pytest

from webapp.runner import AlreadyRunningError, TestRunner, _find_test_result, _persist_iteration_artifacts


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


def test_headed_flag_appends_flag_to_command(tmp_path):
    history_dir = tmp_path / "history"
    captured_cmds = []

    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        captured_cmds.append(cmd)
        return _fake_subprocess_run_factory(history_dir, "pass")(
            cmd, cwd, env, capture_output, text, timeout
        )

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_fake_run)
    batch_id = runner.start(
        "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login",
        "hardware_free",
        1,
        headed=True,
    )
    list(runner.events(batch_id))
    assert "--headed" in captured_cmds[0]
    # nodeid stays at the same index regardless of the flag — callers
    # (e.g. the test fakes above) rely on cmd[3] being the nodeid.
    assert captured_cmds[0][3] == "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"


def test_headed_defaults_false_and_omits_flag(tmp_path):
    history_dir = tmp_path / "history"
    captured_cmds = []

    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        captured_cmds.append(cmd)
        return _fake_subprocess_run_factory(history_dir, "pass")(
            cmd, cwd, env, capture_output, text, timeout
        )

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_fake_run)
    batch_id = runner.start(
        "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login", "hardware_free", 1
    )
    list(runner.events(batch_id))
    assert "--headed" not in captured_cmds[0]


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


def test_failing_run_is_queued_for_review_automatically(tmp_path):
    history_dir = tmp_path / "history"
    findings_path = tmp_path / "netropy-ui-findings.md"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "fail"),
        findings_path=findings_path,
    )
    # No opt-in step — queuing is unconditional and needs no API key.

    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    list(runner.events(batch_id))

    assert findings_path.exists()
    content = findings_path.read_text()
    assert "tests/x.py::test_x" in content
    assert "**Status:** pending review" in content
    assert "Failure message: boom" in content


def test_passing_run_is_not_queued_for_review(tmp_path):
    history_dir = tmp_path / "history"
    findings_path = tmp_path / "netropy-ui-findings.md"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "pass"),
        findings_path=findings_path,
    )

    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    list(runner.events(batch_id))

    assert not findings_path.exists()


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


# --- Bug fix: stale history file must never be mistaken for this
# iteration's result ---
#
# The old `_latest_history_file` picked the newest file in the history
# directory purely by mtime, with no check that the just-run subprocess
# actually produced it. If the subprocess fails to write a new file at
# all (crashed conftest import, collection error, etc.), the prior
# iteration's (or a previous batch's) file would be picked instead, and
# since all iterations of a batch share one nodeid, that stale entry
# would match and get reported as this iteration's outcome — a run that
# never happened silently reported as "passed".


def test_no_new_history_file_reports_error_not_stale_match(tmp_path):
    """A history file for this exact nodeid already exists (e.g. left
    over from a previous batch) recording "pass". The subprocess for the
    new iteration writes nothing at all. The iteration must be reported
    as an error, never matched against the pre-existing stale file."""
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    nodeid = "tests/x.py::test_x"
    stale_file = history_dir / "stale.json"
    stale_file.write_text(
        json.dumps(
            {
                "run_id": "stale",
                "tests": [{"nodeid": nodeid, "outcome": "pass", "failure_message": None}],
            }
        )
    )

    def _writes_nothing(cmd, cwd, env, capture_output, text, timeout):
        class _Result:
            returncode = 1  # crashed before writing any history file

        return _Result()

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_writes_nothing)
    batch_id = runner.start(nodeid, "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "error"
    assert events[1].detail == "No result recorded for this run"
    assert events[2].passed == 0


def test_new_history_file_still_matched_alongside_stale_one(tmp_path):
    """Sanity check for the other side of the fix: when the subprocess
    DOES write a genuine new file, it must still be picked correctly even
    though an older stale file for the same nodeid also sits in the
    directory."""
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    nodeid = "tests/x.py::test_x"
    (history_dir / "stale.json").write_text(
        json.dumps({"run_id": "stale", "tests": [{"nodeid": nodeid, "outcome": "fail", "failure_message": "old failure"}]})
    )

    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "pass"),
    )
    batch_id = runner.start(nodeid, "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "passed"
    assert events[2].passed == 1


# --- Bug fix: artifacts must survive the NEXT pytest session's
# delete_output_dir wipe ---
#
# pytest-playwright's session-scoped, autouse delete_output_dir fixture
# shutil.rmtrees results/artifacts at the start of every session,
# including every later webapp-triggered iteration's own subprocess. The
# runner must copy each iteration's screenshot/trace to a durable,
# batch-scoped location and rewrite the history JSON's paths immediately
# after that iteration completes — not batched at the end.


def _fake_subprocess_run_with_artifacts(history_dir, artifacts_dir, screenshot_rel, trace_rel):
    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        batch_id = env["NETROPY_WEBAPP_BATCH_ID"]
        nodeid = cmd[3]
        history_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"{time.time_ns()}"
        (history_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "batch_id": batch_id,
                    "tests": [
                        {
                            "nodeid": nodeid,
                            "outcome": "fail",
                            "duration": 1.0,
                            "failure_message": "boom",
                            "screenshot": screenshot_rel,
                            "trace": trace_rel,
                        }
                    ],
                }
            )
        )

        class _Result:
            returncode = 1

        return _Result()

    return _fake_run


def test_artifacts_are_copied_to_durable_location_and_json_rewritten(tmp_path):
    repo_root = tmp_path
    results_dir = repo_root / "results"
    artifacts_dir = results_dir / "artifacts"
    test_dir = artifacts_dir / "sometest"
    test_dir.mkdir(parents=True)
    (test_dir / "test-failed-1.png").write_bytes(b"fake-png-bytes")
    (test_dir / "trace.zip").write_bytes(b"fake-trace-bytes")

    history_dir = tmp_path / "history"
    screenshot_rel = "artifacts/sometest/test-failed-1.png"
    trace_rel = "artifacts/sometest/trace.zip"

    runner = TestRunner(
        repo_root=repo_root,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_with_artifacts(
            history_dir, artifacts_dir, screenshot_rel, trace_rel
        ),
    )
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "failed"

    # Exactly one new history file was written; read it back and confirm
    # the stored paths were rewritten to the durable location.
    history_files = list(history_dir.glob("*.json"))
    assert len(history_files) == 1
    data = json.loads(history_files[0].read_text())
    test_entry = data["tests"][0]

    expected_screenshot = f"webapp-artifacts/{batch_id}/1/test-failed-1.png"
    expected_trace = f"webapp-artifacts/{batch_id}/1/trace.zip"
    assert test_entry["screenshot"] == expected_screenshot
    assert test_entry["trace"] == expected_trace

    # The copied files actually exist at the new location, with content
    # intact, and the ORIGINAL artifacts dir is untouched (simulating that
    # a later pytest session's delete_output_dir wipe would not affect
    # this copy).
    assert (results_dir / expected_screenshot).read_bytes() == b"fake-png-bytes"
    assert (results_dir / expected_trace).read_bytes() == b"fake-trace-bytes"
    assert (test_dir / "test-failed-1.png").exists()  # original untouched


def test_persist_iteration_artifacts_no_screenshot_or_trace_is_a_noop(tmp_path):
    """A cleanly-passed test has no screenshot/trace — nothing to copy,
    fields stay None/absent, and no exception is raised."""
    history_file = tmp_path / "run.json"
    test_result = {
        "nodeid": "tests/x.py::test_x",
        "outcome": "pass",
        "screenshot": None,
        "trace": None,
    }
    history_file.write_text(json.dumps({"tests": [test_result]}))

    _persist_iteration_artifacts(history_file, test_result, "batch-1", 1, tmp_path)

    data = json.loads(history_file.read_text())
    assert data["tests"][0]["screenshot"] is None
    assert data["tests"][0]["trace"] is None


def test_persist_iteration_artifacts_missing_source_file_does_not_crash(tmp_path):
    """The source artifact is already gone by copy time (defensive edge
    case) — must not raise, and must not break iteration reporting."""
    history_file = tmp_path / "run.json"
    test_result = {
        "nodeid": "tests/x.py::test_x",
        "outcome": "fail",
        "screenshot": "artifacts/nowhere/test-failed-1.png",
        "trace": None,
    }
    history_file.write_text(json.dumps({"tests": [test_result]}))

    # Should not raise.
    _persist_iteration_artifacts(history_file, test_result, "batch-1", 1, tmp_path)

    # No destination file should have been fabricated.
    assert not (tmp_path / "results" / "webapp-artifacts").exists() or not list(
        (tmp_path / "results" / "webapp-artifacts").rglob("*.png")
    )


def test_multiple_iterations_of_same_test_do_not_overwrite_each_others_screenshots(tmp_path):
    """Two iterations of the same failing test each produce their own
    screenshot at the SAME source path (pytest-playwright reuses the
    slugified test-dir name run to run) — the destination must be keyed
    by iteration number so the second copy doesn't clobber the first."""
    repo_root = tmp_path
    results_dir = repo_root / "results"
    artifacts_dir = results_dir / "artifacts"
    test_dir = artifacts_dir / "sometest"
    history_dir = tmp_path / "history"
    screenshot_rel = "artifacts/sometest/test-failed-1.png"

    calls = {"n": 0}

    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        # Each "subprocess" (re)writes the same source artifact path,
        # exactly as pytest-playwright would across separate sessions.
        calls["n"] += 1
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test-failed-1.png").write_bytes(f"content-for-call-{calls['n']}".encode())
        batch_id = env["NETROPY_WEBAPP_BATCH_ID"]
        nodeid = cmd[3]
        history_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"{time.time_ns()}"
        (history_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "batch_id": batch_id,
                    "tests": [
                        {
                            "nodeid": nodeid,
                            "outcome": "fail",
                            "duration": 1.0,
                            "failure_message": "boom",
                            "screenshot": screenshot_rel,
                            "trace": None,
                        }
                    ],
                }
            )
        )
        time.sleep(0.001)  # ensure distinct history filenames across iterations

        class _Result:
            returncode = 1

        return _Result()

    runner = TestRunner(repo_root=repo_root, history_dir=history_dir, subprocess_run=_fake_run)
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 2)
    list(runner.events(batch_id))

    dest_1 = results_dir / "webapp-artifacts" / batch_id / "1" / "test-failed-1.png"
    dest_2 = results_dir / "webapp-artifacts" / batch_id / "2" / "test-failed-1.png"
    assert dest_1.exists()
    assert dest_2.exists()
    # Each iteration's copy preserved its own content — proof they didn't
    # clobber each other.
    assert dest_1.read_bytes() != dest_2.read_bytes()
