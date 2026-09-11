"""Orchestrates running one test N times via real pytest subprocesses,
tracking live per-iteration status for the SSE endpoint in app.py.
Exactly one batch runs at a time, globally — enforced here, not just
suggested in the UI, since two people could otherwise fight over the
same lab hardware from two browser tabs.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

_OUTCOME_TO_STATUS = {
    "pass": "passed",
    "fail": "failed",
    "error": "error",
    "skip": "skipped",
}


@dataclass
class IterationEvent:
    batch_id: str
    iteration: int
    total: int
    status: str
    detail: Optional[str] = None


@dataclass
class BatchCompleteEvent:
    batch_id: str
    passed: int
    total: int


class AlreadyRunningError(Exception):
    pass


@dataclass
class _Batch:
    id: str
    nodeid: str
    marker: str
    repeat_count: int
    events: "queue.Queue" = field(default_factory=queue.Queue)
    done: bool = False


def _latest_history_file(history_dir: Path) -> Optional[Path]:
    files = sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _find_test_result(history_file: Path, nodeid: str) -> Optional[dict]:
    """Match a triggering nodeid (constructed without a browser-parametrize
    suffix, see catalog.py) against the nodeid actually recorded by
    pytest-playwright, which always carries a `[chromium]`-style suffix.
    Falls back to an exact match in case a nodeid is ever recorded without
    a suffix (e.g. a different browser engine config, or a future
    non-parametrized test)."""
    data = json.loads(history_file.read_text())
    for test in data.get("tests", []):
        stored = test["nodeid"]
        if stored == nodeid or stored.startswith(nodeid + "["):
            return test
    return None


class TestRunner:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        history_dir: Optional[Path] = None,
        subprocess_run=subprocess.run,
    ):
        self._repo_root = repo_root
        self._history_dir = history_dir or (repo_root / "results" / "history")
        self._subprocess_run = subprocess_run
        self._lock = threading.Lock()
        self._active: Optional[_Batch] = None
        self._batches: dict[str, _Batch] = {}

    def start(self, nodeid: str, marker: str, repeat_count: int) -> str:
        with self._lock:
            if self._active is not None and not self._active.done:
                raise AlreadyRunningError(
                    "A test is already running — try again in a moment."
                )
            batch = _Batch(
                id=str(uuid.uuid4()), nodeid=nodeid, marker=marker, repeat_count=repeat_count
            )
            self._active = batch
            self._batches[batch.id] = batch
        thread = threading.Thread(target=self._run_batch, args=(batch,), daemon=True)
        thread.start()
        return batch.id

    def events(self, batch_id: str):
        """Blocking generator the SSE endpoint iterates — yields
        IterationEvents then one final BatchCompleteEvent."""
        batch = self._batches[batch_id]
        while True:
            item = batch.events.get()
            yield item
            if isinstance(item, BatchCompleteEvent):
                return

    def _run_batch(self, batch: _Batch) -> None:
        passed = 0
        for i in range(1, batch.repeat_count + 1):
            batch.events.put(IterationEvent(batch.id, i, batch.repeat_count, "running"))
            env = {**os.environ, "NETROPY_WEBAPP_BATCH_ID": batch.id}
            try:
                self._subprocess_run(
                    [sys.executable, "-m", "pytest", batch.nodeid, "-m", batch.marker],
                    cwd=self._repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                latest = _latest_history_file(self._history_dir)
                test_result = _find_test_result(latest, batch.nodeid) if latest else None
                if test_result is None:
                    status, detail = "error", "No result recorded for this run"
                else:
                    status = _OUTCOME_TO_STATUS.get(test_result["outcome"], "error")
                    detail = test_result.get("failure_message")
            except subprocess.TimeoutExpired:
                status, detail = "error", "Timed out after 10 minutes"
            except Exception as exc:
                status, detail = "error", str(exc)

            if status == "passed":
                passed += 1
            batch.events.put(IterationEvent(batch.id, i, batch.repeat_count, status, detail))

        batch.done = True
        with self._lock:
            if self._active is batch:
                self._active = None
        batch.events.put(BatchCompleteEvent(batch.id, passed, batch.repeat_count))
