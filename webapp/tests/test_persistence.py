"""Run with: pytest --confcutdir=webapp webapp/tests/test_persistence.py -v"""
import json
from pathlib import Path

from webapp.persistence import get_run, list_batches, list_runs_for_nodeid, list_test_runs


def _write_history(
    history_dir: Path,
    run_id: str,
    batch_id,
    nodeid: str,
    outcome: str,
    ts: str,
    run_code=None,
    git_sha="abc123",
    git_branch="main",
    markers="hardware_free",
):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "timestamp": ts,
        "git_sha": git_sha,
        "git_branch": git_branch,
        "markers": markers,
        "duration": 1.5,
        "tests": [
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "duration": 1.5,
                "failure_message": None if outcome == "pass" else "boom",
                "screenshot": None,
                "trace": None,
            }
        ],
    }
    if batch_id:
        data["batch_id"] = batch_id
    if run_code:
        data["run_code"] = run_code
    (history_dir / f"{run_id}.json").write_text(json.dumps(data))


def test_ignores_runs_without_batch_id(tmp_path):
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    assert list_batches(tmp_path) == []


def test_groups_iterations_by_batch_id(tmp_path):
    _write_history(tmp_path, "run1", "batch-a", "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    _write_history(tmp_path, "run2", "batch-a", "tests/x.py::test_x", "fail", "2026-01-01T00:01:00Z")
    _write_history(tmp_path, "run3", "batch-b", "tests/y.py::test_y", "pass", "2026-01-01T00:02:00Z")

    batches = list_batches(tmp_path)
    assert len(batches) == 2
    # newest batch first
    assert batches[0].batch_id == "batch-b"
    assert batches[1].batch_id == "batch-a"

    batch_a = batches[1]
    assert batch_a.nodeid == "tests/x.py::test_x"
    assert len(batch_a.iterations) == 2
    assert batch_a.pass_count == 1
    assert batch_a.total_duration == 3.0
    assert batch_a.started_at == "2026-01-01T00:00:00Z"
    # iterations sorted oldest-first within the batch
    assert [i.outcome for i in batch_a.iterations] == ["pass", "fail"]


def test_skips_malformed_history_file(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "broken.json").write_text("{not valid json")
    _write_history(tmp_path, "run1", "batch-a", "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    batches = list_batches(tmp_path)
    assert len(batches) == 1


def test_list_batches_surfaces_run_code_git_sha_branch_and_markers(tmp_path):
    _write_history(
        tmp_path,
        "run1",
        "batch-a",
        "tests/x.py::test_x",
        "pass",
        "2026-01-01T00:00:00Z",
        run_code="RUN-1",
        git_sha="deadbee",
        git_branch="feature/x",
        markers="hardware_free",
    )
    batches = list_batches(tmp_path)
    assert len(batches) == 1
    batch = batches[0]
    assert batch.run_code == "RUN-1"
    assert batch.git_sha == "deadbee"
    assert batch.git_branch == "feature/x"
    assert batch.markers == "hardware_free"
    assert batch.iterations[0].run_code == "RUN-1"


def test_list_batches_batch_level_fields_come_from_first_run_encountered(tmp_path):
    """A batch groups several sessions/iterations, each with its own
    run_code — the batch-level fields (set once, like nodeid already is)
    come from whichever run created the batch entry first, oldest run
    first per _load_history's sorted glob."""
    _write_history(
        tmp_path, "run1", "batch-a", "tests/x.py::test_x", "pass",
        "2026-01-01T00:00:00Z", run_code="RUN-1",
    )
    _write_history(
        tmp_path, "run2", "batch-a", "tests/x.py::test_x", "fail",
        "2026-01-01T00:01:00Z", run_code="RUN-2",
    )
    batch = list_batches(tmp_path)[0]
    assert batch.run_code == "RUN-1"
    assert [i.run_code for i in batch.iterations] == ["RUN-1", "RUN-2"]


def test_list_batches_new_fields_default_to_none_when_absent(tmp_path):
    """History files written before this feature (or the run_code
    backfill) have none of these fields — must not raise, and must
    surface as None rather than a missing attribute."""
    history_dir = tmp_path
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "run1.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "timestamp": "2026-01-01T00:00:00Z",
                "batch_id": "batch-a",
                "duration": 1.0,
                "tests": [
                    {
                        "nodeid": "tests/x.py::test_x",
                        "outcome": "pass",
                        "duration": 1.0,
                        "failure_message": None,
                        "screenshot": None,
                        "trace": None,
                    }
                ],
            }
        )
    )
    batch = list_batches(history_dir)[0]
    assert batch.run_code is None
    assert batch.git_sha is None
    assert batch.git_branch is None
    assert batch.markers is None
    assert batch.iterations[0].run_code is None


def test_get_run_returns_matching_history_dict(tmp_path):
    _write_history(
        tmp_path, "run1", None, "tests/x.py::test_x", "pass",
        "2026-01-01T00:00:00Z", run_code="RUN-1",
    )
    _write_history(
        tmp_path, "run2", None, "tests/y.py::test_y", "fail",
        "2026-01-01T00:01:00Z", run_code="RUN-2",
    )
    run = get_run("RUN-2", tmp_path)
    assert run is not None
    assert run["run_id"] == "run2"
    assert run["run_code"] == "RUN-2"
    assert run["tests"][0]["nodeid"] == "tests/y.py::test_y"


def test_get_run_returns_none_for_unknown_code(tmp_path):
    _write_history(
        tmp_path, "run1", None, "tests/x.py::test_x", "pass",
        "2026-01-01T00:00:00Z", run_code="RUN-1",
    )
    assert get_run("RUN-999", tmp_path) is None


def test_get_run_returns_none_when_history_dir_missing(tmp_path):
    assert get_run("RUN-1", tmp_path / "does-not-exist") is None


def test_list_test_runs_flattens_every_history_file_newest_first(tmp_path):
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z", run_code="RUN-1")
    _write_history(tmp_path, "run2", None, "tests/y.py::test_y", "fail", "2026-01-01T00:01:00Z", run_code="RUN-2")
    rows = list_test_runs(tmp_path)
    assert [r["run_code"] for r in rows] == ["RUN-2", "RUN-1"]
    assert rows[0]["nodeid"] == "tests/y.py::test_y"
    assert rows[0]["outcome"] == "fail"


def test_list_test_runs_includes_runs_without_batch_id(tmp_path):
    """Unlike list_batches(), this must include plain CLI runs — the
    sibling-run/flaky/overview logic needs the full history, not just
    webapp-triggered runs."""
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z", run_code="RUN-1")
    rows = list_test_runs(tmp_path)
    assert len(rows) == 1


def test_list_runs_for_nodeid_filters_to_one_nodeid(tmp_path):
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z", run_code="RUN-1")
    _write_history(tmp_path, "run2", None, "tests/y.py::test_y", "fail", "2026-01-01T00:01:00Z", run_code="RUN-2")
    _write_history(tmp_path, "run3", None, "tests/x.py::test_x", "fail", "2026-01-01T00:02:00Z", run_code="RUN-3")

    rows = list_runs_for_nodeid("tests/x.py::test_x", tmp_path)
    assert [r["run_code"] for r in rows] == ["RUN-3", "RUN-1"]


def test_list_runs_for_nodeid_returns_empty_for_unknown_nodeid(tmp_path):
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z", run_code="RUN-1")
    assert list_runs_for_nodeid("tests/never/seen.py::test_z", tmp_path) == []
