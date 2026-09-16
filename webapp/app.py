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
import re
import secrets
from collections import defaultdict
from pathlib import Path
from typing import Optional

import markdown
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from webapp.catalog import TestGroup, discover_groups
from webapp.known_issues import (
    STATUS_FIXED,
    STATUS_INVESTIGATING,
    STATUS_OPEN,
    match_failure,
    parse_confirmed_issues,
)
from webapp.persistence import HISTORY_DIR, get_run, list_batches, list_runs_for_nodeid, list_test_runs
from webapp.runner import AlreadyRunningError, IterationEvent, TestRunner
from webapp.trace_summary import extract_trace_summary

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
            "run_code": event.run_code,
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
                "run_code": b.run_code,
                "iterations": [
                    {
                        "run_id": i.run_id,
                        "timestamp": i.timestamp,
                        "outcome": i.outcome,
                        "duration": i.duration,
                        "failure_message": i.failure_message,
                        "screenshot": i.screenshot,
                        "trace": i.trace,
                        "run_code": i.run_code,
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


# --- Run-detail and area-rollup endpoints -----------------------------------
#
# Both build on the same two cheap primitives: catalog.discover_groups()
# (static, from source — the t1_auth/t10_t12_lifecycle-style taxonomy) and
# persistence.list_test_runs() (every history file, flattened to one row
# per test). Neither endpoint keeps any new state — everything is derived
# fresh from what's already on disk.

SIBLING_RUN_LIMIT = 5  # "other runs of this test" — last N, excluding this one
FLAKY_WINDOW = 10  # N-of-last-M rule: disagreement among the last M outcomes

_LEADING_AREA_TOKEN_RE = re.compile(r"^t\d+$")


def _group_area_tokens(group_id: str) -> set[str]:
    """The leading T-number tokens of a catalog group id, e.g.
    "t10_t12_lifecycle" -> {"T10", "T12"} — the same tokens `catalog.py`'s
    `_group_label` reads off the directory name, uppercased to match the
    "T10"-style area `known_issues.py` infers from a finding's body."""
    tokens: set[str] = set()
    for part in group_id.split("_"):
        if _LEADING_AREA_TOKEN_RE.match(part):
            tokens.add(part.upper())
        else:
            break
    return tokens


def _area_for_nodeid(nodeid: str, groups: list[TestGroup]) -> Optional[dict]:
    """Map a test's nodeid back to its catalog group by matching the file
    path (the part of the nodeid before "::") against each group's known
    test files — not by matching the individual test entry, so a test
    that's excluded from the catalog itself (e.g. quarantined, or run out
    of a "_all" combined-suite file `catalog.py` deliberately skips) can
    still resolve an area as long as its *file* belongs to a group.
    Returns None when nothing matches (unknown/combined-suite file) —
    always a possible outcome here, never an error."""
    file_path = nodeid.split("::", 1)[0]
    for group in groups:
        for f in group.files:
            if f.path == file_path:
                return {"id": group.id, "label": group.label}
    return None


def _is_flaky(rows: list[dict]) -> bool:
    """`rows` newest-first for one nodeid (see `list_runs_for_nodeid`) —
    flaky iff the outcomes among the last `FLAKY_WINDOW` disagree rather
    than being uniform (Allure-style N-of-last-M rule)."""
    outcomes = {r["outcome"] for r in rows[:FLAKY_WINDOW]}
    return len(outcomes) > 1


def _known_issue_area_token(nodeid: str, area: Optional[dict]) -> Optional[str]:
    """`known_issues.match_failure`'s `area` parameter expects a single
    "T10"-style token (matching what it infers from a finding's body),
    not a catalog group id like "t10_t12_lifecycle" — a group can bundle
    several T-numbers (see `_group_area_tokens`). For a single-number
    group this is unambiguous; for a multi-number one, prefer whichever
    token literally appears in this test's own file name, falling back to
    the lowest-numbered token so a multi-area group still contributes
    *some* signal rather than none."""
    if not area:
        return None
    tokens = _group_area_tokens(area["id"])
    if not tokens:
        return None
    if len(tokens) == 1:
        return next(iter(tokens))
    file_stem = Path(nodeid.split("::", 1)[0]).stem.lower()
    for token in sorted(tokens):
        if token.lower() in file_stem:
            return token
    return sorted(tokens)[0]


@app.get("/api/runs/{run_code}")
def get_run_detail(run_code: str):
    run = get_run(run_code, HISTORY_DIR)
    if run is None:
        raise HTTPException(404, f"Unknown run: {run_code}")

    groups = discover_groups()
    tests_out = []
    sibling_runs: dict[str, list[dict]] = {}
    any_flaky = False

    for test in run.get("tests", []):
        nodeid = test.get("nodeid")
        outcome = test.get("outcome")
        failure_message = test.get("failure_message")
        area = _area_for_nodeid(nodeid, groups) if nodeid else None

        known_issue_matches: list[dict] = []
        if outcome in ("fail", "error"):
            known_issue_matches = match_failure(
                nodeid, failure_message, _known_issue_area_token(nodeid, area), FINDINGS_PATH
            )

        trace_summary = None
        trace_rel = test.get("trace")
        if outcome in ("fail", "error") and trace_rel:
            trace_path = REPO_ROOT / "results" / trace_rel
            try:
                trace_summary = extract_trace_summary(trace_path)
            except Exception as exc:
                # Best-effort, same defensive posture as failure_review.py —
                # a bad/missing trace must never break the whole endpoint.
                trace_summary = f"(trace could not be read: {exc})"

        rows = list_runs_for_nodeid(nodeid, HISTORY_DIR) if nodeid else []
        if nodeid and nodeid not in sibling_runs:
            sibling_runs[nodeid] = [
                {"run_code": r["run_code"], "timestamp": r["timestamp"], "outcome": r["outcome"]}
                for r in rows
                if r["run_code"] != run_code
            ][:SIBLING_RUN_LIMIT]
        if rows and _is_flaky(rows):
            any_flaky = True

        tests_out.append(
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "duration": test.get("duration", 0.0),
                "failure_message": failure_message,
                "screenshot": test.get("screenshot"),
                "trace": trace_rel,
                "area": area,
                "known_issue_matches": known_issue_matches,
                "trace_summary": trace_summary,
            }
        )

    return {
        "run_code": run.get("run_code"),
        "run_id": run.get("run_id"),
        "timestamp": run.get("timestamp"),
        "git_sha": run.get("git_sha"),
        "git_branch": run.get("git_branch"),
        "markers": run.get("markers"),
        "duration": run.get("duration"),
        "batch_id": run.get("batch_id"),
        "tests": tests_out,
        "sibling_runs": sibling_runs,
        "flaky": any_flaky,
    }


def _matches_catalog_nodeid(catalog_nodeid: str, history_nodeid: str) -> bool:
    """Same nodeid-matching rule as `runner.py`'s `_find_test_result`: a
    catalog nodeid is built from source (no browser-parametrize suffix —
    see catalog.py), but the nodeid pytest-playwright actually records in
    history always carries one, e.g. "...::test_x" vs "...::test_x[chromium]".
    Exact match still allowed as a fallback for an unparametrized test."""
    return history_nodeid == catalog_nodeid or history_nodeid.startswith(catalog_nodeid + "[")


def _rows_for_catalog_nodeid(
    catalog_nodeid: str, rows_by_nodeid: dict[str, list[dict]]
) -> list[dict]:
    matched = [
        row
        for history_nodeid, rows in rows_by_nodeid.items()
        if _matches_catalog_nodeid(catalog_nodeid, history_nodeid)
        for row in rows
    ]
    matched.sort(key=lambda r: r["timestamp"], reverse=True)
    return matched


def _rows_by_nodeid() -> dict[str, list[dict]]:
    """Every history row (see `list_test_runs`), grouped by the *recorded*
    (possibly browser-parametrized) nodeid — the shared starting point
    for both the overview rollup and the area-detail endpoint below."""
    rows_by_nodeid: dict[str, list[dict]] = defaultdict(list)
    for row in list_test_runs(HISTORY_DIR):
        if row["nodeid"]:
            rows_by_nodeid[row["nodeid"]].append(row)
    return rows_by_nodeid


def _status_breakdown(issues: list[dict]) -> dict:
    """`{"open": n, "investigating": n, "fixed": n}` for a list of
    confirmed-issue dicts (each carrying a `status` from
    `known_issues.classify_status`). Always all three keys, even when a
    bucket is empty, so the frontend never has to guess a default."""
    breakdown = {STATUS_OPEN: 0, STATUS_INVESTIGATING: 0, STATUS_FIXED: 0}
    for issue in issues:
        status = issue.get("status", STATUS_OPEN)
        breakdown[status] = breakdown.get(status, 0) + 1
    return breakdown


def _compute_area_rollup(
    group: TestGroup, rows_by_nodeid: dict[str, list[dict]], confirmed_issues: list[dict]
) -> dict:
    """The pass-rate/last-run/flaky-tests/confirmed-issue-count summary
    for one catalog group — shared by `/api/overview` (one of these per
    area) and `/api/areas/{area_id}` (the header of one area's own
    detail page), so the two always agree with each other."""
    nodeids = group.run_all_nodeids
    # rows_by_nodeid is keyed by the *recorded* (possibly
    # browser-suffixed) nodeid; catalog nodeids never carry that suffix,
    # so look each one up via _matches_catalog_nodeid rather than a
    # direct dict hit (see runner.py's _find_test_result).
    per_nid_rows = {nid: _rows_for_catalog_nodeid(nid, rows_by_nodeid) for nid in nodeids}
    group_rows = [r for rows in per_nid_rows.values() for r in rows]

    pass_rate = None
    last_run = None
    if group_rows:
        pass_count = sum(1 for r in group_rows if r["outcome"] == "pass")
        pass_rate = round(pass_count / len(group_rows), 4)
        latest = max(group_rows, key=lambda r: r["timestamp"])
        last_run = {
            "run_code": latest["run_code"],
            "timestamp": latest["timestamp"],
            "outcome": latest["outcome"],
        }

    flaky_tests = [nid for nid, rows in per_nid_rows.items() if _is_flaky(rows)]

    area_tokens = _group_area_tokens(group.id)
    area_issues = [issue for issue in confirmed_issues if issue.get("area") in area_tokens]

    return {
        "id": group.id,
        "label": group.label,
        "pass_rate": pass_rate,
        "last_run": last_run,
        "flaky_tests": flaky_tests,
        # Kept for backward compatibility (webapp/tests/test_run_detail_and_overview.py
        # and test_area_detail.py both assert on this) — always equals the
        # sum of status_breakdown's three buckets.
        "confirmed_issue_count": len(area_issues),
        "status_breakdown": _status_breakdown(area_issues),
    }


@app.get("/api/overview")
def get_overview():
    groups = discover_groups()
    confirmed_issues = parse_confirmed_issues(FINDINGS_PATH)
    rows_by_nodeid = _rows_by_nodeid()
    return {
        "areas": [_compute_area_rollup(g, rows_by_nodeid, confirmed_issues) for g in groups]
    }


@app.get("/api/areas/{area_id}")
def get_area_detail(area_id: str):
    """The Overview area card's click-through target: this area's own
    confirmed known issues (cross-referenced against which of this
    area's tests actually failed/errored with a matching signature) plus
    a full list of the area's tests, each with its latest run. Everything
    here derives from the same two primitives `/api/overview` and
    `/api/runs/{run_code}` already use — catalog.discover_groups() and
    persistence.list_test_runs() — no new state, nothing cached."""
    groups = discover_groups()
    group = next((g for g in groups if g.id == area_id), None)
    if group is None:
        raise HTTPException(404, f"Unknown area: {area_id}")

    confirmed_issues = parse_confirmed_issues(FINDINGS_PATH)
    rows_by_nodeid = _rows_by_nodeid()
    area = {"id": group.id, "label": group.label}
    rollup = _compute_area_rollup(group, rows_by_nodeid, confirmed_issues)

    # --- every test in this area, with its latest run/pass-rate --------
    tests_out = []
    rows_by_test_nodeid: dict[str, list[dict]] = {}
    for f in group.files:
        for t in f.tests:
            rows = _rows_for_catalog_nodeid(t.nodeid, rows_by_nodeid)  # newest-first
            rows_by_test_nodeid[t.nodeid] = rows

            pass_rate = None
            last_run = None
            if rows:
                pass_rate = round(sum(1 for r in rows if r["outcome"] == "pass") / len(rows), 4)
                latest = rows[0]
                last_run = {
                    "run_code": latest["run_code"],
                    "timestamp": latest["timestamp"],
                    "outcome": latest["outcome"],
                }

            tests_out.append(
                {
                    "nodeid": t.nodeid,
                    "name": t.name,
                    "file": f.path,
                    "safety_marker": t.safety_marker,
                    "total_runs": len(rows),
                    "pass_rate": pass_rate,
                    "last_run": last_run,
                }
            )

    # --- this area's confirmed issues, each with its connected tests ---
    area_tokens = _group_area_tokens(group.id)
    issues_out = []
    for issue in confirmed_issues:
        if issue.get("area") not in area_tokens:
            continue
        connected: list[dict] = []
        for f in group.files:
            for t in f.tests:
                token = _known_issue_area_token(t.nodeid, area)
                for row in rows_by_test_nodeid.get(t.nodeid, []):
                    if row["outcome"] not in ("fail", "error"):
                        continue
                    # strict=True: this loop cross-references every
                    # failed/errored run in the area against every one of
                    # the area's confirmed issues — the loose default
                    # floor (fine for one-at-a-time review-queue
                    # suggestions) produces near-blanket matches at that
                    # scale. See known_issues.match_failure's docstring.
                    matches = match_failure(
                        t.nodeid, row.get("failure_message"), token, FINDINGS_PATH, strict=True
                    )
                    if any(m["title"] == issue["title"] for m in matches):
                        connected.append(
                            {
                                "nodeid": t.nodeid,
                                "run_code": row["run_code"],
                                "timestamp": row["timestamp"],
                                "outcome": row["outcome"],
                            }
                        )
        issues_out.append(
            {
                "title": issue["title"],
                "body": issue["body"],
                "status": issue["status"],
                "connected_tests": connected,
            }
        )

    return {
        "id": rollup["id"],
        "label": rollup["label"],
        "pass_rate": rollup["pass_rate"],
        "last_run": rollup["last_run"],
        "flaky_tests": rollup["flaky_tests"],
        "confirmed_issue_count": rollup["confirmed_issue_count"],
        "status_breakdown": rollup["status_breakdown"],
        "known_issues": issues_out,
        "tests": tests_out,
    }


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

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        import anthropic

        runner.enable_failure_review(anthropic.Anthropic(api_key=anthropic_key))
        print("Automatic Claude failure review: enabled (see netropy-ui-findings.md)", flush=True)

    # Passing the app object directly (not the "webapp.app:app" string form)
    # avoids uvicorn re-importing this module under a different name — that
    # second import wouldn't hit this __main__ block, so the middleware just
    # added above would silently vanish from the server uvicorn actually runs.
    uvicorn.run(app, host=host, port=port, reload=False)
