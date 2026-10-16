"""Unit tests for what the Tests tab's area cards are built from: the
catalog's ordering, labels, area/test descriptions, parametrize counts and
WAN detection (webapp/catalog.py), and /api/catalog's per-test last result
(webapp/app.py). Run with:
    pytest --confcutdir=webapp webapp/tests/test_tests_tab.py -v
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webapp.app as app_module
from webapp.catalog import TestEntry, TestFile, TestGroup, _group_label, discover_groups


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _test_file(docstring: str, body: str) -> str:
    return f'"""{docstring}"""\nimport pytest\n\n{body}'


# --- catalog ----------------------------------------------------------------

def test_group_label_keeps_acronyms_upper_case():
    assert _group_label("t15_wan_emulator") == "T15 — WAN Emulator"
    assert _group_label("t14_64b_frame_bad_state") == "T14 — 64B Frame Bad State"


def test_groups_come_in_t_number_order_not_text_order(tmp_path):
    tests_root = tmp_path / "tests"
    for area in ("t10_t12_lifecycle", "t2_dashboard", "t1_auth", "t15_wan_emulator", "wizard"):
        _write(tests_root / area / f"test_{area}_x.py",
               _test_file("x.", "@pytest.mark.hardware_free\ndef test_x(page):\n    pass\n"))
    ids = [g.id for g in discover_groups(tests_root, repo_root=tmp_path)]
    assert ids == ["t1_auth", "t2_dashboard", "t10_t12_lifecycle", "t15_wan_emulator", "wizard"]


def test_area_description_comes_from_init_docstring(tmp_path):
    tests_root = tmp_path / "tests"
    _write(tests_root / "t1_auth" / "__init__.py", '"""Sign-in and sessions."""\n')
    _write(tests_root / "t1_auth" / "test_t1_login.py",
           _test_file("T1 login.", "@pytest.mark.hardware_free\ndef test_t1_login(page):\n    pass\n"))
    _write(tests_root / "t2_dashboard" / "test_t2_loads.py",
           _test_file("T2 loads.", "@pytest.mark.hardware_free\ndef test_t2_loads(page):\n    pass\n"))
    groups = {g.id: g for g in discover_groups(tests_root, repo_root=tmp_path)}
    assert groups["t1_auth"].description == "Sign-in and sessions."
    assert groups["t2_dashboard"].description == ""


def test_descriptions_are_the_first_paragraph_not_the_first_line(tmp_path):
    tests_root = tmp_path / "tests"
    _write(
        tests_root / "t15_wan" / "test_t15_asym.py",
        '''"""T15c: asymmetric delay. 10 ms one way, 80 ms the
other. Real links are asymmetric.

Stateful: real traffic."""
import pytest


@pytest.mark.stateful
def test_t15_asym(wan_bench):
    """Each direction reports its own
    latency.

    Not an average."""
''',
    )
    f = discover_groups(tests_root, repo_root=tmp_path)[0].files[0]
    assert f.short_description == (
        "T15c: asymmetric delay. 10 ms one way, 80 ms the other. Real links are asymmetric."
    )
    assert f.tests[0].description == "Each direction reports its own latency."
    assert "Not an average." in f.tests[0].full_description


def test_param_count_wan_use_and_markers(tmp_path):
    tests_root = tmp_path / "tests"
    _write(
        tests_root / "t16_wan_loss" / "test_t16.py",
        '''"""T16 loss."""
import pytest

CASES = [pytest.param(1, id="a"), pytest.param(2, id="b"), pytest.param(3, id="c")]


@pytest.mark.stateful
@pytest.mark.parametrize("loss_pct", [1, 5])
def test_t16_literal(wan_bench, loss_pct):
    pass


@pytest.mark.stateful
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("size", (64, 128))
def test_t16_named_times_literal(traffic_engine, case, size):
    pass


@pytest.mark.stateful
@pytest.mark.parametrize("case", make_cases())
def test_t16_uncountable(traffic_engine, case):
    pass


@pytest.mark.hardware_free
def test_t16_plain(wan_page):
    pass
''',
    )
    tests = {t.name: t for t in discover_groups(tests_root, repo_root=tmp_path)[0].files[0].tests}
    assert tests["test_t16_literal"].param_count == 2
    assert tests["test_t16_named_times_literal"].param_count == 6
    assert tests["test_t16_uncountable"].param_count == 0
    assert tests["test_t16_plain"].param_count is None
    assert tests["test_t16_literal"].uses_wan and tests["test_t16_plain"].uses_wan
    assert not tests["test_t16_named_times_literal"].uses_wan
    # parametrize is how a test is expanded, not a marker to show or filter on
    assert tests["test_t16_literal"].markers == ["stateful"]


# --- /api/catalog last_result -------------------------------------------------

NODEID = "tests/t16_wan_loss/test_t16.py::test_t16_literal"
NEVER_RUN = "tests/t16_wan_loss/test_t16.py::test_t16_plain"
GROUPS = [
    TestGroup(
        id="t16_wan_loss",
        label="T16 — WAN Loss",
        description="Loss.",
        files=[TestFile(
            path="tests/t16_wan_loss/test_t16.py",
            short_description="T16 loss.",
            full_description="T16 loss.",
            tests=[
                TestEntry(nodeid=NODEID, name="test_t16_literal", markers=["stateful"],
                          description="Loss is counted.", param_count=2, uses_wan=True),
                TestEntry(nodeid=NEVER_RUN, name="test_t16_plain", markers=["hardware_free"]),
            ],
        )],
    ),
]


def _write_session(history_dir: Path, run_id: str, ts: str, run_code: str, outcomes: dict):
    """One pytest session's history file: {recorded nodeid: outcome}."""
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "run_code": run_code, "timestamp": ts, "markers": "stateful",
        "tests": [{"nodeid": n, "outcome": o, "duration": 1.0} for n, o in outcomes.items()],
    }))


@pytest.fixture
def client(monkeypatch, tmp_path):
    history_dir = tmp_path / "history"
    monkeypatch.setattr(app_module, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(app_module, "discover_groups", lambda: GROUPS)
    return TestClient(app_module.app), history_dir


def _tests(c):
    return {t["nodeid"]: t for t in c.get("/api/catalog").json()["groups"][0]["files"][0]["tests"]}


def test_catalog_carries_area_description_and_test_fields(client):
    c, _ = client
    group = c.get("/api/catalog").json()["groups"][0]
    assert group["description"] == "Loss."
    t = _tests(c)[NODEID]
    assert (t["description"], t["param_count"], t["uses_wan"]) == ("Loss is counted.", 2, True)


def test_never_run_test_has_no_last_result(client):
    c, _ = client
    assert _tests(c)[NEVER_RUN]["last_result"] is None


def test_last_result_folds_every_case_of_the_newest_session(client):
    c, history = client
    # An older session failed both cases; the newest has one pass, one fail.
    _write_session(history, "20261001T000000Z", "2026-10-01T00:00:00Z", "RUN-1", {
        f"{NODEID}[chromium-1]": "fail", f"{NODEID}[chromium-5]": "fail",
    })
    _write_session(history, "20261002T000000Z", "2026-10-02T00:00:00Z", "RUN-2", {
        f"{NODEID}[chromium-1]": "pass", f"{NODEID}[chromium-5]": "fail",
    })
    last = _tests(c)[NODEID]["last_result"]
    assert last["outcome"] == "fail"
    assert (last["run_code"], last["cases"], last["passed"]) == ("RUN-2", 2, 1)


def test_last_result_passes_when_every_case_of_the_newest_session_passed(client):
    c, history = client
    _write_session(history, "20261001T000000Z", "2026-10-01T00:00:00Z", "RUN-1", {
        f"{NODEID}[chromium-1]": "fail",
    })
    _write_session(history, "20261002T000000Z", "2026-10-02T00:00:00Z", "RUN-2", {
        f"{NODEID}[chromium-1]": "pass", f"{NODEID}[chromium-5]": "pass",
    })
    last = _tests(c)[NODEID]["last_result"]
    assert (last["outcome"], last["cases"], last["passed"]) == ("pass", 2, 2)


def test_a_session_of_only_skips_reads_skip(client):
    c, history = client
    _write_session(history, "20261002T000000Z", "2026-10-02T00:00:00Z", "RUN-2", {
        f"{NODEID}[chromium-1]": "skip", f"{NODEID}[chromium-5]": "skip",
    })
    assert _tests(c)[NODEID]["last_result"]["outcome"] == "skip"
