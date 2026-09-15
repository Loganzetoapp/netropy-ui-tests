"""FastAPI app: serves the dashboard's static frontend and its small API
— catalog, starting/streaming runs, and reading past results.

Launch with `python -m webapp.app` from the repo root (NOT
`python webapp/app.py` directly — that puts webapp/ itself on sys.path
instead of the repo root, and `from webapp.catalog import ...` would
fail to resolve `webapp` as a package).
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path
from typing import Optional

import markdown
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from webapp.catalog import discover_groups
from webapp.persistence import list_batches
from webapp.runner import AlreadyRunningError, IterationEvent, TestRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Netropy Test Dashboard")
runner = TestRunner()

# (name, icon filename under webapp/static/icons/) — see DESIGN.md's
# "Module tab icons" table for where each one came from.
FUTURE_MODULES = [
    ("Session Strike", "session-strike.png"),
    ("RFC 2544", "rfc-2544.png"),
    ("RFC 9411", "rfc-9411.png"),
    ("AppPlayback", "app-playback.png"),
    ("AppStorm", "app-storm.png"),
    ("DDoS Storm", "ddos-storm.png"),
    ("DNS Storm", "dns-storm.png"),
    ("VoIP / SIP", "voip-sip.png"),
    ("OTT Video", "ott-video.png"),
    ("ThreatStorm", "threatstorm.png"),
    ("PQC", "pqc.png"),
    ("Attack Library", "attack-library.png"),
]


class RunRequest(BaseModel):
    nodeid: str
    repeat_count: int = 1
    headed: bool = False


@app.get("/api/modules")
def get_modules():
    return {
        "modules": [
            {
                "id": "traffic-generator",
                "name": "Traffic Generator",
                "icon": "/static/icons/traffic-engine.png",
                "available": True,
            }
        ]
        + [
            {
                "id": name.lower().replace(" ", "-").replace("/", ""),
                "name": name,
                "icon": f"/static/icons/{icon}",
                "available": False,
            }
            for name, icon in FUTURE_MODULES
        ]
    }


@app.get("/api/catalog")
def get_catalog():
    groups = discover_groups()
    return {
        "groups": [
            {
                "id": g.id,
                "label": g.label,
                "run_all_nodeids": g.run_all_nodeids,
                "files": [
                    {
                        "path": f.path,
                        "short_description": f.short_description,
                        "full_description": f.full_description,
                        "tests": [
                            {
                                "nodeid": t.nodeid,
                                "name": t.name,
                                "markers": t.markers,
                                "safety_marker": t.safety_marker,
                            }
                            for t in f.tests
                        ],
                    }
                    for f in g.files
                ],
            }
            for g in groups
        ]
    }


def _marker_for(nodeid: str) -> str:
    for g in discover_groups():
        for f in g.files:
            for t in f.tests:
                if t.nodeid == nodeid:
                    return t.safety_marker or "hardware_free"
    raise HTTPException(404, f"Unknown test: {nodeid}")


@app.post("/api/runs")
def start_run(req: RunRequest):
    marker = _marker_for(req.nodeid)
    try:
        batch_id = runner.start(req.nodeid, marker, req.repeat_count, req.headed)
    except AlreadyRunningError as exc:
        raise HTTPException(409, str(exc))
    return {"batch_id": batch_id}


def _sse_format(event) -> str:
    if isinstance(event, IterationEvent):
        payload = {
            "type": "iteration",
            "iteration": event.iteration,
            "total": event.total,
            "status": event.status,
            "detail": event.detail,
        }
    else:
        payload = {"type": "batch_complete", "passed": event.passed, "total": event.total}
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/api/runs/{batch_id}/stream")
def stream_run(batch_id: str):
    def generate():
        for event in runner.events(batch_id):
            yield _sse_format(event)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/results")
def get_results():
    batches = list_batches()
    return {
        "batches": [
            {
                "batch_id": b.batch_id,
                "nodeid": b.nodeid,
                "started_at": b.started_at,
                "pass_count": b.pass_count,
                "total": len(b.iterations),
                "total_duration": b.total_duration,
                "iterations": [
                    {
                        "run_id": i.run_id,
                        "timestamp": i.timestamp,
                        "outcome": i.outcome,
                        "duration": i.duration,
                        "failure_message": i.failure_message,
                        "screenshot": i.screenshot,
                        "trace": i.trace,
                    }
                    for i in b.iterations
                ],
            }
            for b in batches
        ]
    }


FINDINGS_PATH = REPO_ROOT / "netropy-ui-findings.md"


@app.get("/api/findings")
def get_findings():
    if not FINDINGS_PATH.exists():
        html = "<p>No findings recorded yet.</p>"
    else:
        html = markdown.markdown(
            FINDINGS_PATH.read_text(), extensions=["fenced_code", "tables"]
        )
    return {"html": html}


class NoCacheStaticFiles(StaticFiles):
    """This app changes frequently during development — a browser that
    caches app.js/styles.css/index.html from before an update can end up
    with, e.g., a nav button that renders (from a freshly-fetched index.html)
    but does nothing (from a stale cached app.js with no listener for it).
    `no-cache` still lets the browser reuse a cached file, but only after
    revalidating with the server (a cheap conditional request against the
    ETag Starlette already sets) — so updates are always picked up on the
    next load, no hard-refresh required, without giving up caching
    entirely. Only applied to /static — /results (screenshots/traces) are
    genuinely immutable once written, so those are fine to cache normally.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# The frontend (index.html, styles.css, app.js, icons, logo) is served
# under /static — matching the paths /api/modules returns and the ones
# index.html itself uses. "/" serves index.html directly so the app
# still opens at the root URL.
app.mount("/results", StaticFiles(directory=str(REPO_ROOT / "results")), name="results")
app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


# --- Sharing this dashboard beyond localhost -------------------------------
#
# By default this only listens on 127.0.0.1 (your own machine) with no
# login — that's unchanged. Sharing it with other people means other
# machines can reach a tool that can trigger real traffic on the lab
# hardware, so that mode requires a login (WEBAPP_USER/WEBAPP_PASSWORD in
# .env) and the server refuses to start without one. See webapp/README.md.
#
# Deliberately kept out of any code that runs at import time (nothing here
# runs unless this file is executed directly) so importing this module for
# tests never depends on ambient .env contents.


def _is_loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def _check_basic_auth(header_value: Optional[str], user: str, password: str) -> bool:
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value[len("Basic "):]).decode("utf-8")
        supplied_user, _, supplied_password = decoded.partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    # constant-time comparison — this gates real traffic on shared hardware
    return secrets.compare_digest(supplied_user, user) and secrets.compare_digest(
        supplied_password, password
    )


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, user: str, password: str):
        super().__init__(app)
        self._user = user
        self._password = password

    async def dispatch(self, request, call_next):
        if _check_basic_auth(request.headers.get("authorization"), self._user, self._password):
            return await call_next(request)
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Netropy Test Dashboard"'},
        )


def _guess_lan_ip() -> Optional[str]:
    """Best-effort LAN-facing IP to print for people sharing this dashboard.
    Opens a UDP "connect" to a public address — this never actually sends a
    packet (UDP connect just picks the local route/interface), it's just the
    standard trick for asking the OS "which of my IPs would this traffic use",
    which is far more reliable than gethostbyname(gethostname()) on machines
    where the hostname resolves to loopback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _validate_sharing_config(host: str, user: Optional[str], password: Optional[str]) -> None:
    """Refuse a non-loopback bind with no credentials configured. This
    dashboard can trigger real traffic on shared lab hardware — opening it
    to the network without a login would let anyone who can reach this
    machine do that. Loopback stays credential-free by default, unchanged."""
    if not _is_loopback_host(host) and not (user and password):
        raise SystemExit(
            f"Refusing to start on host {host!r} (not localhost) without both "
            "WEBAPP_USER and WEBAPP_PASSWORD set in .env — anyone who can reach "
            "this machine could otherwise trigger real traffic on the lab "
            "hardware with no login at all. Set both in .env, or unset WEBAPP_HOST "
            "to go back to localhost-only. See webapp/README.md."
        )


if __name__ == "__main__":
    import socket

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()

    host = os.environ.get("WEBAPP_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBAPP_PORT", "8765"))
    user = os.environ.get("WEBAPP_USER")
    password = os.environ.get("WEBAPP_PASSWORD")

    _validate_sharing_config(host, user, password)
    if user and password:
        app.add_middleware(BasicAuthMiddleware, user=user, password=password)
        print(f"Netropy Test Dashboard (login required): http://{host}:{port}/", flush=True)
    else:
        print(f"Netropy Test Dashboard: http://{host}:{port}/", flush=True)

    if not _is_loopback_host(host):
        lan_ip = _guess_lan_ip()
        if lan_ip:
            print(f"  From another machine on the network: http://{lan_ip}:{port}/", flush=True)

    # Passing the app object directly (not the "webapp.app:app" string form)
    # avoids uvicorn re-importing this module under a different name — that
    # second import wouldn't hit this __main__ block, so the middleware just
    # added above would silently vanish from the server uvicorn actually runs.
    uvicorn.run(app, host=host, port=port, reload=False)
