"""Reads results/history/*.json for the web dashboard's Results page.
Read-only — this never writes; results/history/ is written by the
existing conftest.py pytest_sessionfinish hook (scripts/collect_run.py),
unchanged, for every pytest session including the ones this app
triggers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = REPO_ROOT / "results" / "history"


@dataclass
class IterationResult:
    run_id: str
    timestamp: str
    outcome: str
    duration: float
    failure_message: Optional[str]
    screenshot: Optional[str]
    trace: Optional[str]
    run_code: Optional[str] = None


@dataclass
class BatchResult:
    batch_id: str
    nodeid: str
    iterations: list[IterationResult] = field(default_factory=list)
    # Session-level fields from the FIRST run encountered for this batch —
    # same "set once, at creation" convention as nodeid above. A batch can
    # cover several iterations/history files (one per repeat_count run),
    # each with its own run_code (see IterationResult.run_code for the
    # per-iteration code); these represent the batch as a whole rather
    # than any single iteration.
    run_code: Optional[str] = None
    git_sha: Optional[str] = None
    git_branch: Optional[str] = None
    markers: Optional[str] = None

    @property
    def pass_count(self) -> int:
        return sum(1 for i in self.iterations if i.outcome == "pass")

    @property
    def total_duration(self) -> float:
        return sum(i.duration for i in self.iterations)

    @property
    def started_at(self) -> str:
        return min((i.timestamp for i in self.iterations), default="")


def _load_history(history_dir: Path) -> list[dict]:
    runs = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            runs.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue  # same defensive skip as scripts/build_report.py
    return runs


def list_batches(history_dir: Path = HISTORY_DIR) -> list[BatchResult]:
    """Only web-app-triggered runs (those carrying a batch_id) — plain
    CLI runs have no batch_id and don't belong on this page."""
    batches: dict[str, BatchResult] = {}
    for run in _load_history(history_dir):
        batch_id = run.get("batch_id")
        if not batch_id:
            continue
        for test in run.get("tests", []):
            batch = batches.setdefault(
                batch_id,
                BatchResult(
                    batch_id=batch_id,
                    nodeid=test["nodeid"],
                    run_code=run.get("run_code"),
                    git_sha=run.get("git_sha"),
                    git_branch=run.get("git_branch"),
                    markers=run.get("markers"),
                ),
            )
            batch.iterations.append(
                IterationResult(
                    run_id=run["run_id"],
                    timestamp=run.get("timestamp", ""),
                    outcome=test["outcome"],
                    duration=test.get("duration", 0.0),
                    failure_message=test.get("failure_message"),
                    screenshot=test.get("screenshot"),
                    trace=test.get("trace"),
                    run_code=run.get("run_code"),
                )
            )
    result = list(batches.values())
    for batch in result:
        batch.iterations.sort(key=lambda i: i.timestamp)
    result.sort(key=lambda b: b.started_at, reverse=True)
    return result


def list_test_runs(history_dir: Path = HISTORY_DIR) -> list[dict]:
    """Flatten every history file into one row per (history file, test)
    pair: `run_code`, `run_id`, `timestamp`, `nodeid`, `outcome`,
    `failure_message`. Unlike `list_batches()`, this includes every
    history file — plain CLI runs with no `batch_id` too — since
    sibling-run/flaky-signal/area-rollup logic needs the full picture,
    not just webapp-triggered ones. Sorted newest-first by timestamp.
    This is the raw per-test-run view later endpoints (run-detail
    siblings, the overview rollup, the area-detail known-issue
    cross-reference) fold over. `failure_message` is included alongside
    the original four fields so a caller can run `known_issues.
    match_failure()` against these rows directly without re-reading the
    history file per row — harmless for callers that only used the
    original fields."""
    rows = []
    for run in _load_history(history_dir):
        for test in run.get("tests", []):
            rows.append(
                {
                    "run_code": run.get("run_code"),
                    "run_id": run.get("run_id"),
                    "timestamp": run.get("timestamp", ""),
                    "nodeid": test.get("nodeid"),
                    "outcome": test.get("outcome"),
                    "failure_message": test.get("failure_message"),
                }
            )
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows


def list_runs_for_nodeid(nodeid: str, history_dir: Path = HISTORY_DIR) -> list[dict]:
    """`list_test_runs()` rows for one nodeid only, newest-first — the
    "other runs of this test" chain and the N-of-last-M flaky signal both
    build on this."""
    return [r for r in list_test_runs(history_dir) if r["nodeid"] == nodeid]


def get_run(run_code: str, history_dir: Path = HISTORY_DIR) -> Optional[dict]:
    """Load the single raw history JSON dict whose `run_code` matches, or
    None if no history file carries that code (unknown code, or a
    pre-backfill file that never got one). Linear scan over
    `_load_history` — this repo's history directory is small and local,
    no index is worth the complexity.

    Returns the raw dict close to what's on disk (run_code, run_id,
    timestamp, git_sha, git_branch, markers, duration, tests, batch_id)
    rather than the more processed BatchResult — this is the read
    primitive a later phase's `GET /api/runs/{run_code}` builds on."""
    for run in _load_history(history_dir):
        if run.get("run_code") == run_code:
            return run
    return None
