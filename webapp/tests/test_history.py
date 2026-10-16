"""Unit tests for the Results page's data: /api/history (every run, newest
first, dashboard and command line alike) and /api/history/{run_id} (one
run's tests). Run with:
    pytest --confcutdir=webapp webapp/tests/test_history.py -v
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webapp.app as app_module


def _write(history: Path, run_id: str, ts: str, run_code: str, tests: list, batch_id=None, **extra):
    history.mkdir(parents=True, exist_ok=True)
    data = {"run_id": run_id, "run_code": run_code, "timestamp": ts, "tests": tests, **extra}
    if batch_id:
        data["batch_id"] = batch_id
    (history / f"{run_id}.json").write_text(json.dumps(data))


def _t(name, outcome, message=None):
    return {"nodeid": f"tests/t1/test_x.py::{name}", "outcome": outcome, "duration": 1.5,
            "failure_message": message}


@pytest.fixture
def client(monkeypatch, tmp_path):
    history = tmp_path / "history"
    monkeypatch.setattr(app_module, "HISTORY_DIR", history)
    return TestClient(app_module.app), history


def test_history_lists_every_run_newest_first_with_source(client):
    c, history = client
    _write(history, "r1", "2026-10-15T10:00:00Z", "RUN-1", [_t("a", "pass")], markers="hardware_free")
    _write(history, "r2", "2026-10-16T10:00:00Z", "RUN-2", [_t("a", "pass")], batch_id="b1")
    sessions = c.get("/api/history").json()["sessions"]
    assert [s["run_code"] for s in sessions] == ["RUN-2", "RUN-1"]
    assert [s["source"] for s in sessions] == ["dashboard", "command line"]
    assert sessions[1]["markers"] == "hardware_free"


def test_history_counts_outcomes_and_lists_what_did_not_pass(client):
    c, history = client
    _write(history, "r1", "2026-10-16T10:00:00Z", "RUN-1", [
        _t("ok", "pass"),
        _t("broken", "fail", "AssertionError: expected 2\nmore detail"),
        _t("busy", "skip", "WAN emulator Engine 2 is in use: emulation on"),
    ])
    s = c.get("/api/history").json()["sessions"][0]
    assert s["counts"] == {"pass": 1, "fail": 1, "error": 0, "skip": 1}
    assert s["total"] == 3
    assert {p["name"]: p["reason"] for p in s["problems"]} == {
        "broken": "AssertionError: expected 2",
        "busy": "WAN emulator Engine 2 is in use: emulation on",
    }


def test_history_session_returns_that_runs_tests(client):
    c, history = client
    _write(history, "r1", "2026-10-16T10:00:00Z", "RUN-1", [_t("ok", "pass"), _t("busy", "skip", "ports busy")])
    tests = c.get("/api/history/r1").json()["tests"]
    assert [(t["nodeid"].split("::")[-1], t["outcome"], t["reason"]) for t in tests] == [
        ("ok", "pass", None), ("busy", "skip", "ports busy"),
    ]


def test_history_session_unknown_run_is_404(client):
    c, _ = client
    assert c.get("/api/history/nope").status_code == 404
