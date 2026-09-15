"""Integration tests for GET /api/areas/{area_id}, using FastAPI's
TestClient — same style as test_run_detail_and_overview.py. Run with:
    pytest --confcutdir=webapp webapp/tests/test_area_detail.py -v

History and the findings doc are redirected to tmp fixtures via
monkeypatch (app_module.HISTORY_DIR / app_module.FINDINGS_PATH); the
catalog is redirected by monkeypatching app_module.discover_groups
directly, mirroring test_run_detail_and_overview.py's fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webapp.app as app_module
from webapp.catalog import TestEntry, TestFile, TestGroup

T10_NODEID = "tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py::test_t10_default_addressing_activation"
T10_FILE_PATH = "tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py"
T10B_NODEID = "tests/t10_t12_lifecycle/test_t10_port_conflict_while_active.py::test_t10_port_conflict_while_active"
T10B_FILE_PATH = "tests/t10_t12_lifecycle/test_t10_port_conflict_while_active.py"
T1_NODEID = "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"
T1_FILE_PATH = "tests/t1_auth/test_t1_valid_login.py"

FIXTURE_GROUPS = [
    TestGroup(
        id="t10_t12_lifecycle",
        label="T10/T12 — Lifecycle",
        files=[
            TestFile(
                path=T10_FILE_PATH,
                short_description="T10 — default addressing activation.",
                full_description="T10 — default addressing activation.",
                tests=[
                    TestEntry(
                        nodeid=T10_NODEID,
                        name="test_t10_default_addressing_activation",
                        markers=["stateful"],
                    )
                ],
            ),
            TestFile(
                path=T10B_FILE_PATH,
                short_description="T10 — port conflict while active.",
                full_description="T10 — port conflict while active.",
                tests=[
                    TestEntry(
                        nodeid=T10B_NODEID,
                        name="test_t10_port_conflict_while_active",
                        markers=["stateful"],
                    )
                ],
            ),
        ],
    ),
    TestGroup(
        id="t1_auth",
        label="T1 — Auth",
        files=[
            TestFile(
                path=T1_FILE_PATH,
                short_description="T1 — valid login.",
                full_description="T1 — valid login.",
                tests=[
                    TestEntry(
                        nodeid=T1_NODEID, name="test_t1_valid_login", markers=["hardware_free"]
                    )
                ],
            )
        ],
    ),
]

FIXTURE_FINDINGS = """# Findings

## Confirmed product issues

### Testbed activation returns 502 Bad Gateway for long names
Activation of a testbed fails with a 502 Bad Gateway response when the
testbed name is too long. Confirmed on T10 lifecycle tests during
activation.

### Copy UID silently does nothing
No area token in this one at all — should never attach to any area.
"""


def _write_history(
    history_dir: Path,
    run_id: str,
    nodeid: str,
    outcome: str,
    ts: str,
    run_code: str,
    failure_message=None,
):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "run_code": run_code,
        "timestamp": ts,
        "git_sha": "abc123",
        "git_branch": "main",
        "markers": "stateful",
        "duration": 2.5,
        "tests": [
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "duration": 2.5,
                "failure_message": failure_message,
                "screenshot": None,
                "trace": None,
            }
        ],
    }
    (history_dir / f"{run_id}.json").write_text(json.dumps(data))


@pytest.fixture
def client(monkeypatch, tmp_path):
    history_dir = tmp_path / "history"
    findings_path = tmp_path / "netropy-ui-findings.md"
    findings_path.write_text(FIXTURE_FINDINGS)

    monkeypatch.setattr(app_module, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(app_module, "FINDINGS_PATH", findings_path)
    monkeypatch.setattr(app_module, "discover_groups", lambda: FIXTURE_GROUPS)

    return TestClient(app_module.app), history_dir


def test_unknown_area_id_returns_404(client):
    c, _ = client
    resp = c.get("/api/areas/does-not-exist")
    assert resp.status_code == 404


def test_area_with_no_issues_and_no_runs_is_empty_but_valid(client):
    c, _ = client
    resp = c.get("/api/areas/t1_auth")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "t1_auth"
    assert data["label"] == "T1 — Auth"
    assert data["pass_rate"] is None
    assert data["last_run"] is None
    assert data["flaky_tests"] == []
    assert data["confirmed_issue_count"] == 0
    assert data["known_issues"] == []
    assert len(data["tests"]) == 1
    test = data["tests"][0]
    assert test["nodeid"] == T1_NODEID
    assert test["name"] == "test_t1_valid_login"
    assert test["file"] == T1_FILE_PATH
    assert test["safety_marker"] == "hardware_free"
    assert test["total_runs"] == 0
    assert test["pass_rate"] is None
    assert test["last_run"] is None


def test_area_only_includes_issues_whose_inferred_area_matches(client):
    c, _ = client
    resp = c.get("/api/areas/t10_t12_lifecycle")
    assert resp.status_code == 200
    data = resp.json()
    # "Copy UID silently does nothing" has no inferred area (no T-number
    # in its body) — must never attach itself to this or any area.
    titles = {i["title"] for i in data["known_issues"]}
    assert titles == {"Testbed activation returns 502 Bad Gateway for long names"}


def test_area_issue_lists_its_connected_tests(client):
    c, history_dir = client
    _write_history(
        history_dir,
        "run1",
        T10_NODEID,
        "fail",
        "2026-01-01T00:00:00Z",
        "RUN-1",
        failure_message="502 Bad Gateway activation failed for testbed name",
    )
    # A passing run of the same test must never show up as "connected" —
    # only fail/error runs are cross-referenced against known issues.
    _write_history(
        history_dir, "run2", T10_NODEID, "pass", "2026-01-01T00:01:00Z", "RUN-2"
    )
    # A failing run of a DIFFERENT area's test, even with a failure
    # message that would score a match if it were checked directly
    # (known_issues.match_failure is a loose keyword/area matcher, not
    # scoped by area on its own) — must still never show up here, because
    # the area-detail endpoint only ever cross-references nodeids that
    # belong to *this* catalog group's own files, never the whole history.
    _write_history(
        history_dir,
        "run3",
        T1_NODEID,
        "fail",
        "2026-01-01T00:02:00Z",
        "RUN-3",
        failure_message="502 Bad Gateway activation failed for testbed name",
    )

    resp = c.get("/api/areas/t10_t12_lifecycle")
    assert resp.status_code == 200
    data = resp.json()
    issue = next(
        i
        for i in data["known_issues"]
        if i["title"] == "Testbed activation returns 502 Bad Gateway for long names"
    )
    assert issue["body"]
    assert len(issue["connected_tests"]) == 1
    connected = issue["connected_tests"][0]
    assert connected["nodeid"] == T10_NODEID
    assert connected["run_code"] == "RUN-1"
    assert connected["outcome"] == "fail"


def test_area_tests_list_reflects_latest_run_and_pass_rate(client):
    c, history_dir = client
    _write_history(history_dir, "run1", T1_NODEID, "pass", "2026-01-01T00:00:00Z", "RUN-1")
    _write_history(history_dir, "run2", T1_NODEID, "fail", "2026-01-01T00:01:00Z", "RUN-2")

    resp = c.get("/api/areas/t1_auth")
    test = resp.json()["tests"][0]
    assert test["total_runs"] == 2
    assert test["pass_rate"] == pytest.approx(0.5, rel=1e-3)
    assert test["last_run"] == {
        "run_code": "RUN-2",
        "timestamp": "2026-01-01T00:01:00Z",
        "outcome": "fail",
    }


def test_area_rollup_matches_overview_for_same_area(client):
    """The header fields on the area-detail page (pass_rate, last_run,
    flaky_tests, confirmed_issue_count) must agree with the Overview
    card that links into it — both are built from the same
    _compute_area_rollup helper."""
    c, history_dir = client
    for i, outcome in enumerate(["pass", "fail", "pass"], start=1):
        _write_history(
            history_dir, f"run{i}", T1_NODEID, outcome, f"2026-01-01T00:0{i}:00Z", f"RUN-{i}"
        )

    overview_area = next(
        a for a in c.get("/api/overview").json()["areas"] if a["id"] == "t1_auth"
    )
    area_detail = c.get("/api/areas/t1_auth").json()

    assert area_detail["pass_rate"] == overview_area["pass_rate"]
    assert area_detail["last_run"] == overview_area["last_run"]
    assert area_detail["flaky_tests"] == overview_area["flaky_tests"]
    assert area_detail["confirmed_issue_count"] == overview_area["confirmed_issue_count"]
