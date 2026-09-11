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


@dataclass
class BatchResult:
    batch_id: str
    nodeid: str
    iterations: list[IterationResult] = field(default_factory=list)

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
                batch_id, BatchResult(batch_id=batch_id, nodeid=test["nodeid"])
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
                )
            )
    result = list(batches.values())
    for batch in result:
        batch.iterations.sort(key=lambda i: i.timestamp)
    result.sort(key=lambda b: b.started_at, reverse=True)
    return result
