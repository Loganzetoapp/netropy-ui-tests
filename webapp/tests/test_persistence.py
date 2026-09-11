"""Run with: pytest --confcutdir=webapp webapp/tests/test_persistence.py -v"""
import json
from pathlib import Path

from webapp.persistence import list_batches


def _write_history(history_dir: Path, run_id: str, batch_id, nodeid: str, outcome: str, ts: str):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "timestamp": ts,
        "git_sha": "abc123",
        "git_branch": "main",
        "markers": "hardware_free",
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
