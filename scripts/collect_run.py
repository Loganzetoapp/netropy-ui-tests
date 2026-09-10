"""Collect one pytest run's results into results/history/<run-id>.json.

Normally invoked automatically by conftest.py's pytest_sessionfinish hook
right after a test session finishes (see conftest.py — it runs `trylast`
so results/junit.xml, written by pytest's own junitxml plugin, is already
on disk by the time this reads it). Can also be run by hand:

    python scripts/collect_run.py [--markers "hardware_free"]

for a one-off pass over the most recent results/junit.xml, e.g. to
re-collect after editing a run's XML by hand. The live conftest hook path
is authoritative — it knows the real `-m` expression from pytest's own
config; the CLI has to be told, since a bare junit.xml doesn't record it.

History files are small and deliberately committed (see .gitignore) so
the dashboard has real history across clones — junit.xml and screenshots
themselves stay gitignored, raw and regenerable.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JUNIT = ROOT / "results" / "junit.xml"
DEFAULT_HISTORY_DIR = ROOT / "results" / "history"
DEFAULT_ARTIFACTS_DIR = ROOT / "results" / "artifacts"
FAILURE_MESSAGE_LIMIT = 500


def _git(*args: str) -> Optional[str]:
    """Run a git command from the repo root; None on any failure (never raise —
    a missing git binary or a detached/weird state shouldn't break collection)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


def _screenshot_for(nodeid: str, artifacts_dir: Path) -> Optional[str]:
    """Path (relative to results/) to the failure screenshot conftest.py's
    `page` fixture would have saved for this test, if it exists: naming is
    <--output dir>/<artifact_paths.slugify(nodeid)>/test-failed-<n>.png —
    see the `page` fixture in conftest.py for why this suite writes its
    own screenshots rather than relying on pytest-playwright's (for this
    repo, inert) built-in mechanism. Wrapped defensively anyway, since a
    screenshot link is a nice-to-have, not something collection should
    ever fail over.
    """
    try:
        from scripts.artifact_paths import slugify
    except Exception:
        return None
    test_dir = artifacts_dir / slugify(nodeid)
    if not test_dir.is_dir():
        return None
    # only-on-failure is this repo's configured mode, but handle "on" too
    # (test-finished-N.png) by just taking whatever's there, failed first.
    for pattern in ("test-failed-*.png", "test-finished-*.png"):
        matches = sorted(test_dir.glob(pattern))
        if matches:
            try:
                return str(matches[0].relative_to(artifacts_dir.parent))
            except ValueError:
                return str(matches[0])
    return None


def _parse_testcase(tc: ET.Element, artifacts_dir: Path) -> dict:
    nodeid_file = tc.get("classname", "").replace(".", "/")
    # classname is dotted-module form (tests.t10_x.test_y); junit's own
    # "file" attribute (when present) is the real path and more reliable
    # than reconstructing one, so prefer it.
    file_path = tc.get("file")
    name = tc.get("name", "")
    if file_path:
        nodeid = f"{file_path}::{name}"
    else:
        nodeid = f"{nodeid_file}.py::{name}"

    duration = float(tc.get("time", 0.0) or 0.0)

    failure_el = tc.find("failure")
    error_el = tc.find("error")
    skipped_el = tc.find("skipped")

    if failure_el is not None:
        outcome = "fail"
        msg = failure_el.get("message") or (failure_el.text or "")
    elif error_el is not None:
        outcome = "error"
        msg = error_el.get("message") or (error_el.text or "")
    elif skipped_el is not None:
        outcome = "skip"
        msg = skipped_el.get("message") or (skipped_el.text or "")
    else:
        outcome = "pass"
        msg = None

    failure_message = msg.strip()[:FAILURE_MESSAGE_LIMIT] if msg else None

    return {
        "nodeid": nodeid,
        "outcome": outcome,
        "duration": duration,
        "failure_message": failure_message,
        "screenshot": _screenshot_for(nodeid, artifacts_dir),
    }


def build_summary(
    junit_path: Path = DEFAULT_JUNIT,
    markers: str = "",
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    run_time: Optional[datetime] = None,
) -> Optional[dict]:
    """Parse junit_path into a history summary dict, or None if it can't be
    read/parsed (missing file, no tests ran, malformed XML)."""
    if not junit_path.exists():
        return None

    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError:
        return None

    # junit's root is <testsuites> wrapping one or more <testsuite> — pytest
    # only ever writes one, but don't assume it.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    if not suites:
        return None

    tests = []
    total_duration = 0.0
    for suite in suites:
        total_duration += float(suite.get("time", 0.0) or 0.0)
        for tc in suite.findall("testcase"):
            tests.append(_parse_testcase(tc, artifacts_dir))

    if not tests:
        return None

    now = run_time or datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")

    return {
        "run_id": run_id,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "--short", "HEAD") or "unknown",
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "markers": markers or "",
        "duration": round(total_duration, 3),
        "tests": tests,
    }


def write_summary(summary: dict, history_dir: Path = DEFAULT_HISTORY_DIR) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    out_path = history_dir / f"{summary['run_id']}.json"
    # Extremely unlikely (same-second collisions) but cheap to guard: don't
    # clobber a real prior run's file if two collections land in the same
    # second (e.g. two quick pytest invocations back to back).
    suffix = 2
    while out_path.exists():
        out_path = history_dir / f"{summary['run_id']}-{suffix}.json"
        suffix += 1
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    return out_path


def collect(
    junit_path: Path = DEFAULT_JUNIT,
    history_dir: Path = DEFAULT_HISTORY_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    markers: str = "",
) -> Optional[Path]:
    """High-level entry point: parse + write. Returns the written path, or
    None if there was nothing collectible (never raises)."""
    summary = build_summary(junit_path, markers=markers, artifacts_dir=artifacts_dir)
    if summary is None:
        return None
    return write_summary(summary, history_dir)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markers",
        default="",
        help="The -m marker expression this run used (not recoverable from "
        "junit.xml itself — the live conftest hook knows this directly; "
        "pass it explicitly for a manual/standalone collection).",
    )
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    args = parser.parse_args()

    path = collect(
        junit_path=args.junit,
        history_dir=args.history_dir,
        artifacts_dir=args.artifacts_dir,
        markers=args.markers,
    )
    if path is None:
        print(f"collect_run: nothing to collect from {args.junit} (missing or empty)")
        return 1
    print(f"collect_run: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
