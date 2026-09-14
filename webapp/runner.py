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
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from webapp import failure_review

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
    headed: bool = False
    events: "queue.Queue" = field(default_factory=queue.Queue)
    done: bool = False


def _snapshot_history_files(history_dir: Path) -> set[Path]:
    """The set of history files that exist right before an iteration's
    subprocess runs, so the file(s) that subprocess itself produces can
    be told apart from anything already sitting in the directory. See
    _new_history_file — this is the other half of that guard."""
    if not history_dir.exists():
        return set()
    return set(history_dir.glob("*.json"))


def _new_history_file(history_dir: Path, before: set[Path]) -> Optional[Path]:
    """Pick the newest history file that did NOT already exist in `before`.

    Bug fix: picking the newest file in the directory purely by mtime, with
    no check that it was actually produced by the iteration that just ran,
    is unsafe. If the triggered pytest subprocess
    fails to produce a new history file at all (e.g. a missing/rotated
    .env taking the whole session out at conftest import time, a
    collection/usage error, or build_summary returning None because
    nothing ran), the old code would silently fall back to the PRIOR
    iteration's (or even a previous batch's) file — and since all
    iterations of one batch share the same nodeid, that stale file's
    entry would match and get reported as the current iteration's
    outcome. A run that never happened could be silently reported as
    "passed". This only ever considers files that are new since `before`,
    so a subprocess that produces nothing yields None here, which the
    caller must treat as a genuine error, never a stale-file fallback."""
    after = _snapshot_history_files(history_dir)
    new_files = after - before
    if not new_files:
        return None
    return max(new_files, key=lambda p: p.stat().st_mtime)


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


def _persist_iteration_artifacts(
    history_file: Path,
    test_result: dict,
    batch_id: str,
    iteration: int,
    repo_root: Path,
) -> None:
    """Copy this iteration's screenshot/trace out of results/artifacts into
    a batch-scoped, permanent location, and rewrite the stored paths in
    the history JSON on disk to point there.

    Bug fix: pytest-playwright ships a session-scoped, autouse
    `delete_output_dir` fixture that shutil.rmtrees the --output directory
    (results/artifacts) at the START of every pytest session. Every
    webapp-triggered iteration is its own pytest subprocess/session, so
    iteration N of a batch deletes iterations 1..N-1's screenshots/traces,
    and any later run of any test deletes every earlier batch's artifacts
    too. This must run right after each iteration's subprocess completes
    (before the next iteration's subprocess can wipe results/artifacts
    again), not batched at the end.

    Downstream readers (persistence.list_batches, /api/results, the
    frontend Results page) need no changes — they just read whatever path
    is in the JSON file, and this makes that path durable.
    """
    results_dir = repo_root / "results"
    dest_dir = results_dir / "webapp-artifacts" / batch_id / str(iteration)
    stored_nodeid = test_result.get("nodeid")
    new_paths: dict[str, Optional[str]] = {}

    for key in ("screenshot", "trace"):
        rel_path = test_result.get(key)
        if not rel_path:
            continue  # nothing to copy — passed cleanly, leave untouched
        source = results_dir / rel_path
        if not source.exists():
            # Defensive only — expected to exist since we're copying it
            # immediately after the subprocess that produced it finished.
            # Never let a missing artifact break pass/fail reporting.
            print(f"webapp runner: artifact missing, cannot preserve: {source}")
            new_paths[key] = None
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / Path(rel_path).name
            shutil.copy2(source, dest)
        except OSError as exc:
            print(f"webapp runner: failed to preserve artifact {source}: {exc}")
            continue
        new_paths[key] = str(dest.relative_to(results_dir))

    if not new_paths:
        return

    data = json.loads(history_file.read_text())
    for test in data.get("tests", []):
        if test.get("nodeid") == stored_nodeid:
            test.update(new_paths)
            test_result.update(new_paths)
            break
    history_file.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


class TestRunner:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        history_dir: Optional[Path] = None,
        subprocess_run=subprocess.run,
        findings_path: Optional[Path] = None,
    ):
        self._repo_root = repo_root
        self._history_dir = history_dir or (repo_root / "results" / "history")
        self._subprocess_run = subprocess_run
        self._lock = threading.Lock()
        self._active: Optional[_Batch] = None
        self._batches: dict[str, _Batch] = {}
        self._findings_path = findings_path or (repo_root / "netropy-ui-findings.md")

    def start(
        self, nodeid: str, marker: str, repeat_count: int, headed: bool = False
    ) -> str:
        with self._lock:
            if self._active is not None and not self._active.done:
                raise AlreadyRunningError(
                    "A test is already running — try again in a moment."
                )
            batch = _Batch(
                id=str(uuid.uuid4()),
                nodeid=nodeid,
                marker=marker,
                repeat_count=repeat_count,
                headed=headed,
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
            before = _snapshot_history_files(self._history_dir)
            test_result: Optional[dict] = None
            cmd = [sys.executable, "-m", "pytest", batch.nodeid, "-m", batch.marker]
            if batch.headed:
                cmd.append("--headed")
            try:
                self._subprocess_run(
                    cmd,
                    cwd=self._repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                history_file = _new_history_file(self._history_dir, before)
                test_result = (
                    _find_test_result(history_file, batch.nodeid) if history_file else None
                )
                if test_result is None:
                    status, detail = "error", "No result recorded for this run"
                else:
                    status = _OUTCOME_TO_STATUS.get(test_result["outcome"], "error")
                    detail = test_result.get("failure_message")
                    try:
                        _persist_iteration_artifacts(
                            history_file, test_result, batch.id, i, self._repo_root
                        )
                    except Exception as exc:
                        # Artifact preservation is best-effort — never let
                        # it break pass/fail reporting for this iteration.
                        print(f"webapp runner: artifact preservation failed: {exc}")
            except subprocess.TimeoutExpired:
                status, detail = "error", "Timed out after 10 minutes"
            except Exception as exc:
                status, detail = "error", str(exc)

            if status == "passed":
                passed += 1
            batch.events.put(IterationEvent(batch.id, i, batch.repeat_count, status, detail))

            if status in ("failed", "error"):
                self._queue_failure_review(batch.nodeid, detail, test_result)

        batch.done = True
        with self._lock:
            if self._active is batch:
                self._active = None
        batch.events.put(BatchCompleteEvent(batch.id, passed, batch.repeat_count))

    def _queue_failure_review(
        self, nodeid: str, detail: Optional[str], test_result: Optional[dict]
    ) -> None:
        """Best-effort: log this failed iteration's evidence into
        netropy-ui-findings.md's pending-review queue (no API call — see
        failure_review.py). Any failure here (malformed trace, disk
        error, ...) is logged and swallowed — a failure logging a failure
        must never itself break run reporting."""
        screenshot_rel = test_result.get("screenshot") if test_result else None
        trace_rel = test_result.get("trace") if test_result else None
        trace_path = (self._repo_root / "results" / trace_rel) if trace_rel else None
        try:
            failure_review.queue_pending_review(
                self._findings_path, nodeid, detail, screenshot_rel, trace_rel, trace_path
            )
        except Exception as exc:
            print(f"webapp runner: queuing failure review failed: {exc}")
