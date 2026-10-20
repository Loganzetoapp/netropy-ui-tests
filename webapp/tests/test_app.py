"""Integration tests for the API surface using FastAPI's TestClient — no
real subprocess, no real pytest run. Run with:
    pytest --confcutdir=webapp webapp/tests/test_app.py -v
"""
import pytest
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
        def start(self, nodeid, marker, repeat_count, headed=False, target_url=None):
            captured["headed"] = headed
            captured["target_url"] = target_url
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


def test_target_url_is_normalized_and_passed_through(monkeypatch):
    captured = {}

    class _CapturingRunner:
        def start(self, nodeid, marker, repeat_count, headed=False, target_url=None):
            captured["target_url"] = target_url
            return "batch-1"

    monkeypatch.setattr(app_module, "runner", _CapturingRunner())
    client = TestClient(app_module.app)
    nodeid = client.get("/api/catalog").json()["groups"][0]["files"][0]["tests"][0]["nodeid"]

    resp = client.post("/api/runs", json={"nodeid": nodeid, "target_url": " 10.1.2.3:8080 "})
    assert resp.status_code == 200
    assert captured["target_url"] == "http://10.1.2.3:8080"

    resp = client.post("/api/runs", json={"nodeid": nodeid})
    assert resp.status_code == 200
    assert captured["target_url"] is None


@pytest.mark.parametrize(
    "bad",
    ["ftp://10.0.0.1", "http://user:pw@10.0.0.1", "http://10.0.0.1/login", "not a host!", "http://10.0.0.1:99999"],
)
def test_bad_target_url_is_rejected(monkeypatch, bad):
    class _NeverRunner:
        def start(self, *a, **k):
            raise AssertionError("should not start")

    monkeypatch.setattr(app_module, "runner", _NeverRunner())
    client = TestClient(app_module.app)
    nodeid = client.get("/api/catalog").json()["groups"][0]["files"][0]["tests"][0]["nodeid"]
    resp = client.post("/api/runs", json={"nodeid": nodeid, "target_url": bad})
    assert resp.status_code == 422


def test_targets_endpoint_lists_presets_and_default(monkeypatch):
    monkeypatch.setenv("NETROPY_URL", "http://192.168.173.212/")
    data = TestClient(app_module.app).get("/api/targets").json()
    assert data["default"] == "http://192.168.173.212"
    assert any(p["url"] == "http://192.168.173.212" for p in data["presets"])


def test_findings_endpoint_includes_investigation_log(monkeypatch, tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text("# Findings\n")
    log = tmp_path / "log.md"
    log.write_text("# Investigation\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    monkeypatch.setattr(app_module, "FINDINGS_PATH", findings)
    monkeypatch.setattr(app_module, "INVESTIGATION_LOG_PATH", log)
    data = TestClient(app_module.app).get("/api/findings").json()
    assert "<h1>Investigation</h1>" in data["investigation_html"]
    assert "<table>" in data["investigation_html"]

    monkeypatch.setattr(app_module, "INVESTIGATION_LOG_PATH", tmp_path / "missing.md")
    assert TestClient(app_module.app).get("/api/findings").json()["investigation_html"] is None


def test_ensure_port_free_passes_on_an_unused_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    app_module._ensure_port_free("127.0.0.1", free_port)  # must not raise


def test_ensure_port_free_refuses_a_port_another_process_is_listening_on():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        taken_port = listener.getsockname()[1]
        with pytest.raises(SystemExit, match="already in use"):
            app_module._ensure_port_free("127.0.0.1", taken_port)
