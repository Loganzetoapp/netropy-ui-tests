"""Unit tests for the webapp-related additions to scripts/collect_run.py
(batch_id tagging, trace-file lookup). Run with:
    pytest --confcutdir=webapp webapp/tests/test_collect_run_extensions.py -v
"""
import os
from pathlib import Path

from scripts.collect_run import _trace_for, build_summary


def _write_junit(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0"?>'
        '<testsuites><testsuite time="1.5">'
        '<testcase classname="tests.t1_auth.test_t1_valid_login" '
        'name="test_t1_valid_login[chromium]" time="1.5" '
        'file="tests/t1_auth/test_t1_valid_login.py" /></testsuite></testsuites>'
    )


def test_build_summary_omits_batch_id_when_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("NETROPY_WEBAPP_BATCH_ID", raising=False)
    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    summary = build_summary(junit, artifacts_dir=tmp_path / "artifacts")
    assert "batch_id" not in summary


def test_build_summary_includes_batch_id_when_passed(tmp_path):
    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    summary = build_summary(junit, artifacts_dir=tmp_path / "artifacts", batch_id="abc-123")
    assert summary["batch_id"] == "abc-123"


def test_trace_for_finds_existing_trace(tmp_path):
    from scripts.artifact_paths import slugify

    nodeid = "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"
    artifacts_dir = tmp_path / "artifacts"
    trace_dir = artifacts_dir / slugify(nodeid)
    trace_dir.mkdir(parents=True)
    (trace_dir / "trace.zip").write_bytes(b"fake")

    result = _trace_for(nodeid, artifacts_dir)
    assert result == f"artifacts/{slugify(nodeid)}/trace.zip"


def test_trace_for_returns_none_when_absent(tmp_path):
    assert _trace_for("tests/x.py::test_x", tmp_path / "artifacts") is None
