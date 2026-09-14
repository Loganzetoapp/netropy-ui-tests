"""Integration tests for the API surface using FastAPI's TestClient — no
real subprocess, no real pytest run. Run with:
    pytest --confcutdir=webapp webapp/tests/test_app.py -v
"""
from fastapi.testclient import TestClient

import webapp.app as app_module


def test_modules_endpoint_lists_traffic_generator_and_twelve_future_modules():
    client = TestClient(app_module.app)
    data = client.get("/api/modules").json()
    assert len(data["modules"]) == 13
    assert data["modules"][0] == {
        "id": "traffic-generator",
        "name": "Traffic Generator",
        "icon": "/static/icons/traffic-engine.png",
        "available": True,
    }
    assert all(m["available"] is False for m in data["modules"][1:])
    assert all(m["icon"].startswith("/static/icons/") for m in data["modules"])


def test_catalog_endpoint_returns_real_groups():
    client = TestClient(app_module.app)
    data = client.get("/api/catalog").json()
    ids = {g["id"] for g in data["groups"]}
    assert "t1_auth" in ids


def test_findings_endpoint_renders_markdown_to_html(monkeypatch, tmp_path):
    findings_file = tmp_path / "netropy-ui-findings.md"
    findings_file.write_text("# Findings\n\n## Confirmed product issues\n\nSomething real.\n")
    monkeypatch.setattr(app_module, "FINDINGS_PATH", findings_file)

    client = TestClient(app_module.app)
    data = client.get("/api/findings").json()

    assert "<h1>Findings</h1>" in data["html"]
    assert "<h2>Confirmed product issues</h2>" in data["html"]
    assert "Something real." in data["html"]


def test_findings_endpoint_handles_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "FINDINGS_PATH", tmp_path / "does-not-exist.md")

    client = TestClient(app_module.app)
    data = client.get("/api/findings").json()

    assert "No findings recorded yet" in data["html"]


def test_unknown_nodeid_returns_404():
    client = TestClient(app_module.app)
    resp = client.post(
        "/api/runs", json={"nodeid": "tests/does/not/exist.py::nope", "repeat_count": 1}
    )
    assert resp.status_code == 404


def test_headed_flag_defaults_false_and_passes_through(monkeypatch):
    import webapp.runner as runner_module

    captured = {}

    class _CapturingRunner:
        def start(self, nodeid, marker, repeat_count, headed=False):
            captured["headed"] = headed
            return "batch-1"

    monkeypatch.setattr(app_module, "runner", _CapturingRunner())
    client = TestClient(app_module.app)
    groups = client.get("/api/catalog").json()["groups"]
    nodeid = groups[0]["files"][0]["tests"][0]["nodeid"]

    resp = client.post("/api/runs", json={"nodeid": nodeid, "repeat_count": 1})
    assert resp.status_code == 200
    assert captured["headed"] is False

    resp = client.post("/api/runs", json={"nodeid": nodeid, "repeat_count": 1, "headed": True})
    assert resp.status_code == 200
    assert captured["headed"] is True


def test_second_concurrent_run_returns_409(monkeypatch):
    import webapp.runner as runner_module

    class _AlwaysBusyRunner:
        def start(self, *a, **k):
            raise runner_module.AlreadyRunningError("busy")

    monkeypatch.setattr(app_module, "runner", _AlwaysBusyRunner())
    client = TestClient(app_module.app)
    groups = client.get("/api/catalog").json()["groups"]
    nodeid = groups[0]["files"][0]["tests"][0]["nodeid"]
    resp = client.post("/api/runs", json={"nodeid": nodeid, "repeat_count": 1})
    assert resp.status_code == 409
