"""Tests for scripts/backfill_run_codes.py — the one-off migration that
assigns run_code to pre-existing results/history/*.json files. Run with:
    pytest --confcutdir=webapp webapp/tests/test_backfill_run_codes.py -v
"""
import json
from pathlib import Path

from scripts.backfill_run_codes import backfill
from scripts.collect_run import _next_run_code


def _write(history_dir: Path, run_id: str, **extra):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {"run_id": run_id, "tests": []}
    data.update(extra)
    (history_dir / f"{run_id}.json").write_text(json.dumps(data))


def test_backfill_assigns_codes_in_chronological_run_id_order(tmp_path):
    history_dir = tmp_path / "history"
    # Written out of filename/creation order on purpose.
    _write(history_dir, "20260901T000000Z")
    _write(history_dir, "20260801T000000Z")
    _write(history_dir, "20260915T000000Z")

    backfill(history_dir)

    codes = {p.stem: json.loads(p.read_text())["run_code"] for p in history_dir.glob("*.json")}
    assert codes["20260801T000000Z"] == "RUN-1"
    assert codes["20260901T000000Z"] == "RUN-2"
    assert codes["20260915T000000Z"] == "RUN-3"


def test_backfill_skips_files_that_already_have_a_run_code(tmp_path):
    history_dir = tmp_path / "history"
    _write(history_dir, "20260801T000000Z", run_code="RUN-99")
    _write(history_dir, "20260901T000000Z")

    touched = backfill(history_dir)

    assert touched == ["20260901T000000Z.json"]
    already_coded = json.loads((history_dir / "20260801T000000Z.json").read_text())
    assert already_coded["run_code"] == "RUN-99"  # untouched
    newly_coded = json.loads((history_dir / "20260901T000000Z.json").read_text())
    # The real counter is independent of any hand-set run_code already in
    # a file, so this starts at 1, not 100.
    assert newly_coded["run_code"] == "RUN-1"


def test_backfill_is_idempotent(tmp_path):
    history_dir = tmp_path / "history"
    _write(history_dir, "20260801T000000Z")
    _write(history_dir, "20260901T000000Z")

    first = backfill(history_dir)
    assert len(first) == 2
    before = {p.stem: json.loads(p.read_text())["run_code"] for p in history_dir.glob("*.json")}

    second = backfill(history_dir)
    assert second == []  # nothing left to do

    after = {p.stem: json.loads(p.read_text())["run_code"] for p in history_dir.glob("*.json")}
    assert before == after  # no code was reassigned or changed


def test_backfill_continues_sequence_from_existing_counter(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    (history_dir / ".run_seq").write_text("10")
    _write(history_dir, "20260801T000000Z")

    backfill(history_dir)

    data = json.loads((history_dir / "20260801T000000Z.json").read_text())
    assert data["run_code"] == "RUN-11"


def test_backfill_dry_run_does_not_write_or_advance_counter(tmp_path):
    history_dir = tmp_path / "history"
    _write(history_dir, "20260801T000000Z")

    touched = backfill(history_dir, dry_run=True)
    assert touched == ["20260801T000000Z.json"]

    data = json.loads((history_dir / "20260801T000000Z.json").read_text())
    assert "run_code" not in data
    # The counter must not have been consumed by the dry run.
    assert _next_run_code(history_dir) == "RUN-1"


def test_backfill_skips_malformed_history_file(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "broken.json").write_text("{not valid json")
    _write(history_dir, "20260801T000000Z")

    touched = backfill(history_dir)
    assert touched == ["20260801T000000Z.json"]


def test_backfill_ignores_the_run_seq_counter_file_itself(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    (history_dir / ".run_seq").write_text("0")
    _write(history_dir, "20260801T000000Z")

    touched = backfill(history_dir)
    assert touched == ["20260801T000000Z.json"]
