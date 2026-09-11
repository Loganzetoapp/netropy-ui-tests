"""FastAPI app: serves the dashboard's static frontend and its small API
— catalog, starting/streaming runs, and reading past results.

Launch with `python -m webapp.app` from the repo root (NOT
`python webapp/app.py` directly — that puts webapp/ itself on sys.path
instead of the repo root, and `from webapp.catalog import ...` would
fail to resolve `webapp` as a package).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


# The frontend (index.html, styles.css, app.js, icons, logo) is served
# under /static — matching the paths /api/modules returns and the ones
# index.html itself uses. "/" serves index.html directly so the app
# still opens at the root URL.
app.mount("/results", StaticFiles(directory=str(REPO_ROOT / "results")), name="results")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webapp.app:app", host="127.0.0.1", port=8765, reload=False)
