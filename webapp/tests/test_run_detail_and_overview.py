"""Integration tests for GET /api/runs/{run_code} and GET /api/overview,
using FastAPI's TestClient — same style as test_app.py. Run with:
    pytest --confcutdir=webapp webapp/tests/test_run_detail_and_overview.py -v

History and the findings doc are redirected to tmp fixtures via
monkeypatch (app_module.HISTORY_DIR / app_module.FINDINGS_PATH); the
catalog is redirected by monkeypatching app_module.discover_groups
directly, building TestGroup/TestFile/TestEntry fixtures in code rather
than writing real test files to disk — cheaper and keeps area-mapping
assertions explicit about which nodeid maps to which group.
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
                        markers=["hardware_free"],
                    )
                ],
            )
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
"""


def _write_history(
    history_dir: Path,
    run_id: str,
    nodeid: str,
    outcome: str,
    ts: str,
    run_code: str,
    failure_message=None,
    trace=None,
    batch_id=None,
):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "run_code": run_code,
        "timestamp": ts,
        "git_sha": "abc123",
        "git_branch": "main",
        "markers": "hardware_free",
        "duration": 2.5,
        "tests": [
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "duration": 2.5,
                "failure_message": failure_message,
                "screenshot": None,
                "trace": trace,
            }
        ],
    }
    if batch_id:
        data["batch_id"] = batch_id
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


# --- GET /api/runs/{run_code} ------------------------------------------------


def test_get_run_detail_unknown_code_returns_404(client):
    c, _ = client
    resp = c.get("/api/runs/RUN-999")
    assert resp.status_code == 404


def test_get_run_detail_happy_path_passing_run_has_no_matches_or_trace_summary(client):
    c, history_dir = client
    _write_history(history_dir, "run1", T1_NODEID, "pass", "2026-01-01T00:00:00Z", "RUN-1")

    resp = c.get("/api/runs/RUN-1")
    assert resp.status_code == 200
    data = resp.json()

    assert data["run_code"] == "RUN-1"
    assert data["run_id"] == "run1"
    assert data["git_sha"] == "abc123"
    assert data["git_branch"] == "main"
    assert data["markers"] == "hardware_free"
    assert data["duration"] == 2.5
    assert data["flaky"] is False

    assert len(data["tests"]) == 1
    test = data["tests"][0]
    assert test["nodeid"] == T1_NODEID
    assert test["outcome"] == "pass"
    assert test["area"] == {"id": "t1_auth", "label": "T1 — Auth"}
    # a passing test never gets known-issue matches or a trace summary,
    # even though a matching finding exists in the fixture doc — matching
    # only ever runs for fail/error outcomes.
    assert test["known_issue_matches"] == []
    assert test["trace_summary"] is None

    assert data["sibling_runs"] == {T1_NODEID: []}


def test_get_run_detail_failing_run_surfaces_known_issue_match(client):
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

    resp = c.get("/api/runs/RUN-1")
    assert resp.status_code == 200
    test = resp.json()["tests"][0]
    assert test["outcome"] == "fail"
    assert test["area"] == {"id": "t10_t12_lifecycle", "label": "T10/T12 — Lifecycle"}
    assert len(test["known_issue_matches"]) == 1
    assert (
        test["known_issue_matches"][0]["title"]
        == "Testbed activation returns 502 Bad Gateway for long names"
    )
    assert test["known_issue_matches"][0]["label"] == "possible match — review"


def test_get_run_detail_failing_run_with_no_matching_issue_returns_empty_list(client):
    c, history_dir = client
    _write_history(
        history_dir,
        "run1",
        T1_NODEID,
        "fail",
        "2026-01-01T00:00:00Z",
        "RUN-1",
        failure_message="widget color assertion failed",
    )
    resp = c.get("/api/runs/RUN-1")
    test = resp.json()["tests"][0]
    assert test["known_issue_matches"] == []


def test_get_run_detail_unknown_area_when_nodeid_not_in_catalog(client):
    """A nodeid from a combined "_all" suite file (or any file the
    catalog doesn't know about) must resolve to area: null, not an
    error."""
    c, history_dir = client
    unknown_nodeid = "tests/t1_auth/test_t1_auth_all.py::test_t1_valid_login"
    _write_history(history_dir, "run1", unknown_nodeid, "pass", "2026-01-01T00:00:00Z", "RUN-1")

    resp = c.get("/api/runs/RUN-1")
    assert resp.status_code == 200
    assert resp.json()["tests"][0]["area"] is None


def test_get_run_detail_sibling_runs_excludes_self_and_caps_at_five(client):
    c, history_dir = client
    for i in range(1, 8):
        _write_history(
            history_dir,
            f"run{i}",
            T1_NODEID,
            "pass",
            f"2026-01-01T00:0{i}:00Z",
            f"RUN-{i}",
        )

    resp = c.get("/api/runs/RUN-7")
    siblings = resp.json()["sibling_runs"][T1_NODEID]
    assert len(siblings) == 5
    assert all(s["run_code"] != "RUN-7" for s in siblings)
    # newest-first
    assert siblings[0]["run_code"] == "RUN-6"


def test_get_run_detail_flags_flaky_when_outcomes_disagree(client):
    c, history_dir = client
    outcomes = ["pass", "pass", "fail", "pass", "pass"]
    for i, outcome in enumerate(outcomes, start=1):
        _write_history(
            history_dir,
            f"run{i}",
            T1_NODEID,
            outcome,
            f"2026-01-01T00:0{i}:00Z",
            f"RUN-{i}",
        )

    resp = c.get("/api/runs/RUN-5")
    assert resp.json()["flaky"] is True


def test_get_run_detail_not_flaky_when_outcomes_uniform(client):
    c, history_dir = client
    for i in range(1, 4):
        _write_history(
            history_dir, f"run{i}", T1_NODEID, "pass", f"2026-01-01T00:0{i}:00Z", f"RUN-{i}"
        )
    resp = c.get("/api/runs/RUN-3")
    assert resp.json()["flaky"] is False


def test_get_run_detail_trace_read_failure_is_caught_not_raised(client):
    """A trace path that exists in the history JSON but not on disk (or
    isn't a valid zip) must never break the endpoint — best-effort,
    mirroring failure_review.py's own defensive posture."""
    c, history_dir = client
    _write_history(
        history_dir,
        "run1",
        T1_NODEID,
        "fail",
        "2026-01-01T00:00:00Z",
        "RUN-1",
        failure_message="boom",
        trace="artifacts/does-not-exist/trace.zip",
    )
    resp = c.get("/api/runs/RUN-1")
    assert resp.status_code == 200
    test = resp.json()["tests"][0]
    assert test["trace_summary"] is not None
    assert "could not be read" in test["trace_summary"]


# --- GET /api/overview -------------------------------------------------------


def test_overview_returns_all_catalog_groups(client):
    c, history_dir = client
    resp = c.get("/api/overview")
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["areas"]}
    assert ids == {"t10_t12_lifecycle", "t1_auth"}


def test_overview_area_with_no_history_has_null_pass_rate_and_last_run(client):
    c, history_dir = client
    resp = c.get("/api/overview")
    t1 = next(a for a in resp.json()["areas"] if a["id"] == "t1_auth")
    assert t1["pass_rate"] is None
    assert t1["last_run"] is None
    assert t1["flaky_tests"] == []


def test_overview_matches_browser_parametrized_nodeids(client):
    """Real history nodeids always carry pytest-playwright's parametrize
    suffix (e.g. "...::test_t1_valid_login[chromium]"), but catalog
    nodeids (built from source, see catalog.py) never do — the same
    mismatch `runner.py`'s `_find_test_result` already handles for
    iteration status matching. Without normalizing for it, group_rows
    would always come up empty against real history and every area would
    show a null pass rate."""
    c, history_dir = client
    _write_history(
        history_dir, "run1", f"{T1_NODEID}[chromium]", "pass", "2026-01-01T00:00:00Z", "RUN-1"
    )
    _write_history(
        history_dir, "run2", f"{T1_NODEID}[chromium]", "fail", "2026-01-01T00:01:00Z", "RUN-2"
    )

    resp = c.get("/api/overview")
    t1 = next(a for a in resp.json()["areas"] if a["id"] == "t1_auth")
    assert t1["pass_rate"] == pytest.approx(0.5, rel=1e-3)
    assert t1["last_run"]["run_code"] == "RUN-2"
    assert t1["flaky_tests"] == [T1_NODEID]


def test_overview_computes_pass_rate_and_last_run(client):
    c, history_dir = client
    _write_history(history_dir, "run1", T1_NODEID, "pass", "2026-01-01T00:00:00Z", "RUN-1")
    _write_history(history_dir, "run2", T1_NODEID, "fail", "2026-01-01T00:01:00Z", "RUN-2")
    _write_history(history_dir, "run3", T1_NODEID, "pass", "2026-01-01T00:02:00Z", "RUN-3")

    resp = c.get("/api/overview")
    t1 = next(a for a in resp.json()["areas"] if a["id"] == "t1_auth")
    assert t1["pass_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert t1["last_run"] == {"run_code": "RUN-3", "timestamp": "2026-01-01T00:02:00Z", "outcome": "pass"}


def test_overview_flags_flaky_tests(client):
    c, history_dir = client
    for i, outcome in enumerate(["pass", "fail", "pass"], start=1):
        _write_history(
            history_dir, f"run{i}", T1_NODEID, outcome, f"2026-01-01T00:0{i}:00Z", f"RUN-{i}"
        )
    resp = c.get("/api/overview")
    t1 = next(a for a in resp.json()["areas"] if a["id"] == "t1_auth")
    assert t1["flaky_tests"] == [T1_NODEID]


def test_overview_counts_confirmed_issues_by_area(client):
    c, history_dir = client
    resp = c.get("/api/overview")
    areas = {a["id"]: a for a in resp.json()["areas"]}
    # the fixture findings doc's one confirmed issue is inferred as T10 —
    # only the t10_t12_lifecycle group (which owns T10) should count it.
    assert areas["t10_t12_lifecycle"]["confirmed_issue_count"] == 1
    assert areas["t1_auth"]["confirmed_issue_count"] == 0


def test_overview_handles_missing_findings_file(monkeypatch, tmp_path):
    history_dir = tmp_path / "history"
    monkeypatch.setattr(app_module, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(app_module, "FINDINGS_PATH", tmp_path / "does-not-exist.md")
    monkeypatch.setattr(app_module, "discover_groups", lambda: FIXTURE_GROUPS)

    c = TestClient(app_module.app)
    resp = c.get("/api/overview")
    assert resp.status_code == 200
    assert all(a["confirmed_issue_count"] == 0 for a in resp.json()["areas"])
