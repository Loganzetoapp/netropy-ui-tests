"""Build results/index.html from every results/history/*.json summary.

    python scripts/build_report.py              # results/history -> results/index.html
    python scripts/build_report.py --history-dir X --out Y.html

Runs automatically after every pytest session (see conftest.py's
pytest_sessionfinish hook, which calls collect() then build() — "one
command, zero extra steps"). This module is also the manual rebuild path
(`make report`), e.g. after pulling new history/*.json from someone else's
branch without re-running any tests locally.

Single self-contained HTML file: inline CSS, inline SVG charts (hand-built
here, not a JS charting library), inline vanilla JS for the filters. No
CDN, no server, no build step — opens directly via file://. Pure stdlib.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY_DIR = ROOT / "results" / "history"
DEFAULT_OUT = ROOT / "results" / "index.html"

AREA_RE = re.compile(r"^(t\d+)", re.IGNORECASE)
TREND_WINDOW = 30
SLOWEST_TOP_N = 10
FLAKY_DISPLAY_CAP = 25


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_all_runs(history_dir: Path) -> list[dict]:
    """Every valid run summary in history_dir, sorted oldest -> newest. A
    malformed file is skipped with a warning, never fatal — one bad JSON
    file (partial write, manual edit gone wrong) shouldn't take the whole
    dashboard down."""
    runs = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"build_report: WARNING skipping unreadable {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict) or "tests" not in data or "run_id" not in data:
            print(f"build_report: WARNING skipping malformed {path}", file=sys.stderr)
            continue
        data.setdefault("_source", path.name)
        runs.append(data)
    runs.sort(key=lambda r: (r.get("timestamp") or "", r.get("run_id") or ""))
    return runs


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------

def area_of(nodeid: str) -> str:
    """'tests/t10_t12_lifecycle/test_x.py::test_y[chromium]' -> 't10'."""
    for part in nodeid.split("::")[0].split("/"):
        m = AREA_RE.match(part)
        if m:
            return m.group(1).lower()
    return "other"


def is_pass(outcome: str) -> bool:
    return outcome == "pass"


def is_failing(outcome: str) -> bool:
    return outcome in ("fail", "error")


def fmt_duration(seconds: float) -> str:
    seconds = seconds or 0.0
    if seconds >= 60:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {s:04.1f}s"
    return f"{seconds:.1f}s"


def fmt_ts(ts: str) -> str:
    # Stored as "2026-09-10T17:30:45Z" — just make it a touch more readable.
    return ts.replace("T", " ").replace("Z", " UTC") if ts else "—"


# --------------------------------------------------------------------------
# Section 1/2 data: header + trend
# --------------------------------------------------------------------------

def run_totals(run: dict) -> dict:
    tests = run.get("tests", [])
    total = len(tests)
    passed = sum(1 for t in tests if is_pass(t["outcome"]))
    failed = sum(1 for t in tests if is_failing(t["outcome"]))
    skipped = sum(1 for t in tests if t["outcome"] == "skip")
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": (passed / total * 100.0) if total else 0.0,
    }


def compute_trend(runs: list[dict], window: int = TREND_WINDOW) -> list[dict]:
    windowed = runs[-window:]
    out = []
    for run in windowed:
        totals = run_totals(run)
        out.append(
            {
                "run_id": run["run_id"],
                "timestamp": run.get("timestamp", ""),
                "sha": run.get("git_sha", "?"),
                "pass_rate": totals["pass_rate"],
                "duration": run.get("duration", 0.0),
                "total": totals["total"],
            }
        )
    return out


# --------------------------------------------------------------------------
# Section 3: back-to-back / stability sessions
# --------------------------------------------------------------------------

def compute_stability_sessions(runs: list[dict]) -> list[dict]:
    """Group runs by git SHA; keep only SHAs with 2+ runs (a real
    back-to-back stability session — a single run on a SHA has nothing to
    be stable/flaky *across*). Newest session first."""
    by_sha: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        by_sha[run.get("git_sha", "unknown")].append(run)

    sessions = []
    for sha, sha_runs in by_sha.items():
        if len(sha_runs) < 2:
            continue
        sha_runs = sorted(sha_runs, key=lambda r: r.get("timestamp", ""))

        per_test: dict[str, list[dict]] = defaultdict(list)
        for run in sha_runs:
            marker = run.get("markers", "")
            for t in run.get("tests", []):
                per_test[t["nodeid"]].append(
                    {
                        "outcome": t["outcome"],
                        "duration": t.get("duration", 0.0),
                        "marker": marker,
                    }
                )

        rows = []
        for nodeid, attempts in per_test.items():
            passes = sum(1 for a in attempts if is_pass(a["outcome"]))
            fails = sum(1 for a in attempts if is_failing(a["outcome"]))
            n = len(attempts)
            flaky = passes > 0 and fails > 0
            symbols = []
            for a in attempts:
                if is_pass(a["outcome"]):
                    symbols.append(("ok", "✓"))  # check
                elif is_failing(a["outcome"]):
                    symbols.append(("bad", "✗"))  # cross
                else:
                    symbols.append(("skip", "○"))  # circle
            rows.append(
                {
                    "nodeid": nodeid,
                    "area": area_of(nodeid),
                    "marker": attempts[-1]["marker"] if attempts else "",
                    "attempts": n,
                    "pass_pct": (passes / n * 100.0) if n else 0.0,
                    "flaky": flaky,
                    "sparkline": symbols,
                    "last_outcome": attempts[-1]["outcome"],
                }
            )
        # Flaky first, then by lowest stability, then name — surfaces the
        # thing you actually need to look at right at the top.
        rows.sort(key=lambda r: (not r["flaky"], r["pass_pct"], r["nodeid"]))

        latest = sha_runs[-1]
        sessions.append(
            {
                "sha": sha,
                "branch": latest.get("git_branch", "?"),
                "run_count": len(sha_runs),
                "first_ts": sha_runs[0].get("timestamp", ""),
                "last_ts": latest.get("timestamp", ""),
                "rows": rows,
                "flaky_count": sum(1 for r in rows if r["flaky"]),
            }
        )

    sessions.sort(key=lambda s: s["last_ts"], reverse=True)
    return sessions


# --------------------------------------------------------------------------
# Section 4: flaky ranking across ALL history
# --------------------------------------------------------------------------

def compute_global_flaky(runs: list[dict]) -> list[dict]:
    per_test: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        marker = run.get("markers", "")
        ts = run.get("timestamp", "")
        for t in run.get("tests", []):
            per_test[t["nodeid"]].append(
                {"outcome": t["outcome"], "duration": t.get("duration", 0.0), "ts": ts, "marker": marker}
            )

    results = []
    for nodeid, appearances in per_test.items():
        appearances.sort(key=lambda a: a["ts"])
        # Flips are computed over the pass/not-pass sequence with skips
        # dropped out entirely — a skip is neither a pass nor a failure,
        # so it shouldn't count as (or break) a flip.
        sequence = [is_pass(a["outcome"]) for a in appearances if a["outcome"] != "skip"]
        flips = sum(1 for i in range(1, len(sequence)) if sequence[i] != sequence[i - 1])
        if flips == 0:
            continue
        non_skip_durations = [a["duration"] for a in appearances if a["outcome"] != "skip"]
        avg_duration = statistics.fmean(non_skip_durations) if non_skip_durations else 0.0
        results.append(
            {
                "nodeid": nodeid,
                "area": area_of(nodeid),
                "marker": appearances[-1]["marker"],
                "flips": flips,
                "avg_duration": avg_duration,
                "score": flips * avg_duration,
                "attempts": len(appearances),
                "last_outcome": appearances[-1]["outcome"],
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# --------------------------------------------------------------------------
# Section 5: slowest tests + trend vs historical median
# --------------------------------------------------------------------------

def compute_slowest(runs: list[dict]) -> list[dict]:
    per_test: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        ts = run.get("timestamp", "")
        for t in run.get("tests", []):
            if t["outcome"] == "skip":
                continue  # a skip's ~0s duration isn't a meaningful sample
            per_test[t["nodeid"]].append({"duration": t.get("duration", 0.0), "ts": ts})

    rows = []
    for nodeid, appearances in per_test.items():
        appearances.sort(key=lambda a: a["ts"])
        durations = [a["duration"] for a in appearances]
        recent = durations[-1]
        median = statistics.median(durations)
        if median > 0 and recent > median * 1.05:
            trend = "up"
        elif median > 0 and recent < median * 0.95:
            trend = "down"
        else:
            trend = "flat"
        rows.append(
            {
                "nodeid": nodeid,
                "area": area_of(nodeid),
                "recent_duration": recent,
                "median_duration": median,
                "trend": trend,
                "samples": len(durations),
            }
        )
    rows.sort(key=lambda r: r["recent_duration"], reverse=True)
    return rows[:SLOWEST_TOP_N]


# --------------------------------------------------------------------------
# Section 6: latest run's failures
# --------------------------------------------------------------------------

def compute_latest_failures(latest_run: Optional[dict]) -> list[dict]:
    if not latest_run:
        return []
    out = []
    for t in latest_run.get("tests", []):
        if is_failing(t["outcome"]):
            out.append(
                {
                    "nodeid": t["nodeid"],
                    "area": area_of(t["nodeid"]),
                    "marker": latest_run.get("markers", ""),
                    "outcome": t["outcome"],
                    "duration": t.get("duration", 0.0),
                    "failure_message": t.get("failure_message") or "(no message captured)",
                    "screenshot": t.get("screenshot"),
                }
            )
    return out


# --------------------------------------------------------------------------
# SVG chart rendering (no JS charting lib — plain server-rendered SVG)
# --------------------------------------------------------------------------

def render_line_chart(
    points: list[float],
    labels: list[str],
    *,
    y_min: float,
    y_max: float,
    width: int = 760,
    height: int = 160,
    color: str,
    unit: str = "",
    fmt=lambda v: f"{v:.1f}",
) -> str:
    if not points:
        return '<p class="empty">No runs yet.</p>'

    pad_l, pad_r, pad_t, pad_b = 36, 12, 14, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(points)
    span = (y_max - y_min) or 1.0

    def x_at(i: int) -> float:
        return pad_l + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y_at(v: float) -> float:
        return pad_t + plot_h - ((v - y_min) / span * plot_h)

    coords = [(x_at(i), y_at(v)) for i, v in enumerate(points)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area_path = (
        f"M{coords[0][0]:.1f},{pad_t + plot_h:.1f} "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in coords)
        + f" L{coords[-1][0]:.1f},{pad_t + plot_h:.1f} Z"
    )

    circles = []
    for (x, y), v, label in zip(coords, points, labels):
        title = html.escape(f"{label}: {fmt(v)}{unit}")
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" class="pt">'
            f"<title>{title}</title></circle>"
        )

    gridlines = []
    n_grid = 4
    for g in range(n_grid + 1):
        gy = pad_t + plot_h * g / n_grid
        gv = y_max - span * g / n_grid
        gridlines.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" class="grid"/>'
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" class="axis" text-anchor="end">{fmt(gv)}{unit}</text>'
        )

    return f"""
<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" class="chart" preserveAspectRatio="xMidYMid meet">
  {''.join(gridlines)}
  <path d="{area_path}" class="area" style="fill:{color}"/>
  <polyline points="{poly}" class="line" style="stroke:{color}"/>
  {''.join(circles)}
</svg>"""


# --------------------------------------------------------------------------
# HTML assembly
# --------------------------------------------------------------------------

def _sparkline_html(symbols: list[tuple[str, str]]) -> str:
    return "".join(f'<span class="spark {cls}">{ch}</span>' for cls, ch in symbols)


def _trend_arrow(trend: str) -> str:
    return {"up": '<span class="arrow up">▲</span>', "down": '<span class="arrow down">▼</span>', "flat": '<span class="arrow flat">▬</span>'}[trend]


def render_html(runs: list[dict], history_dir: Path) -> str:
    latest = runs[-1] if runs else None
    totals = run_totals(latest) if latest else {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0}
    trend = compute_trend(runs)
    sessions = compute_stability_sessions(runs)
    flaky = compute_global_flaky(runs)
    slowest = compute_slowest(runs)
    failures = compute_latest_failures(latest)

    all_markers = sorted({r.get("markers", "") for r in runs if r.get("markers")})
    all_areas = sorted({area_of(t["nodeid"]) for r in runs for t in r.get("tests", [])})

    # ---- header ----
    if latest is None:
        header = '<div class="empty"><h1>No runs yet</h1><p>Run <code>pytest -m hardware_free</code> once to populate this dashboard.</p></div>'
    else:
        status = "PASS" if totals["failed"] == 0 else "FAIL"
        status_class = "ok" if status == "PASS" else "bad"
        header = f"""
<div class="header-grid">
  <div class="status-badge {status_class}">{status}</div>
  <div class="header-meta">
    <div class="run-line">
      <span class="mono">{html.escape(latest.get('git_sha', '?'))}</span>
      <span class="sep">&middot;</span>
      <span>{html.escape(latest.get('git_branch', '?'))}</span>
      <span class="sep">&middot;</span>
      <span class="pill">{html.escape(latest.get('markers') or '(no -m)')}</span>
    </div>
    <div class="run-line dim">{fmt_ts(latest.get('timestamp', ''))}</div>
    <div class="run-stats">
      <b>{totals['passed']}</b>/{totals['total']} passed
      <span class="sep">&middot;</span>
      {totals['failed']} failed
      <span class="sep">&middot;</span>
      {totals['skipped']} skipped
      <span class="sep">&middot;</span>
      {fmt_duration(latest.get('duration', 0.0))}
    </div>
  </div>
</div>"""

    # ---- trend charts ----
    if trend:
        pr_labels = [fmt_ts(t["timestamp"]) for t in trend]
        pr_points = [t["pass_rate"] for t in trend]
        dur_points = [t["duration"] for t in trend]
        pass_chart = render_line_chart(
            pr_points, pr_labels, y_min=0, y_max=100, color="var(--ok)", unit="%",
            fmt=lambda v: f"{v:.0f}",
        )
        max_dur = max(dur_points) if dur_points else 1.0
        dur_chart = render_line_chart(
            dur_points, pr_labels, y_min=0, y_max=max(max_dur * 1.1, 1.0), color="var(--accent)",
            unit="s", fmt=lambda v: f"{v:.0f}",
        )
    else:
        pass_chart = dur_chart = '<p class="empty">No runs yet.</p>'

    trend_section = f"""
<section id="trend">
  <h2>Trend <span class="dim">— last {len(trend)} run{'s' if len(trend) != 1 else ''}</span></h2>
  <div class="chart-grid">
    <div class="chart-card">
      <h3>Pass rate</h3>
      {pass_chart}
    </div>
    <div class="chart-card">
      <h3>Total duration</h3>
      {dur_chart}
    </div>
  </div>
</section>"""

    # ---- stability sessions ----
    if sessions:
        options = "".join(
            f'<option value="{i}">{html.escape(s["sha"])} &middot; {s["run_count"]} runs'
            f'{" &middot; " + str(s["flaky_count"]) + " flaky" if s["flaky_count"] else ""}</option>'
            for i, s in enumerate(sessions)
        )
        session_blocks = []
        for i, s in enumerate(sessions):
            rows_html = []
            for r in s["rows"]:
                flaky_badge = '<span class="badge bad">FLAKY</span>' if r["flaky"] else ""
                rows_html.append(
                    f'<tr data-marker="{html.escape(r["marker"])}" data-area="{r["area"]}" '
                    f'data-outcome="{r["last_outcome"]}" class="{"flaky-row" if r["flaky"] else ""}">'
                    f'<td class="mono nodeid">{html.escape(r["nodeid"])}</td>'
                    f'<td>{flaky_badge}</td>'
                    f'<td>{r["attempts"]}</td>'
                    f'<td>{r["pass_pct"]:.0f}%</td>'
                    f'<td class="spark-cell">{_sparkline_html(r["sparkline"])}</td>'
                    f"</tr>"
                )
            display = "" if i == 0 else ' style="display:none"'
            session_blocks.append(
                f'<div class="session-block" data-session-index="{i}"{display}>'
                f'<p class="dim">{html.escape(s["branch"])} &middot; {fmt_ts(s["first_ts"])} &rarr; {fmt_ts(s["last_ts"])} &middot; {s["run_count"]} runs</p>'
                f'<table class="stability-table"><thead><tr>'
                f"<th>Test</th><th></th><th>Attempts</th><th>Pass %</th><th>Recent outcomes</th>"
                f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>"
            )
        stability_section = f"""
<section id="stability">
  <h2>Stability sessions <span class="dim">— runs sharing one git SHA</span></h2>
  <label class="session-picker">Session:
    <select id="session-select" onchange="showSession(this.value)">{options}</select>
  </label>
  {''.join(session_blocks)}
</section>"""
    else:
        stability_section = """
<section id="stability">
  <h2>Stability sessions <span class="dim">— runs sharing one git SHA</span></h2>
  <p class="empty">No back-to-back sessions yet — run the suite 2+ times on the same commit to populate this
  (see "Stability run" in CLAUDE.md).</p>
</section>"""

    # ---- global flaky ranking ----
    if flaky:
        shown = flaky[:FLAKY_DISPLAY_CAP]
        flaky_rows = "".join(
            f'<tr data-marker="{html.escape(r["marker"])}" data-area="{r["area"]}" data-outcome="{r["last_outcome"]}">'
            f'<td class="mono nodeid">{html.escape(r["nodeid"])}</td>'
            f'<td>{r["flips"]}</td>'
            f'<td>{fmt_duration(r["avg_duration"])}</td>'
            f'<td>{r["score"]:.1f}</td>'
            f'<td>{r["attempts"]}</td>'
            f"</tr>"
            for r in shown
        )
        note = (
            f'<p class="dim">Showing top {len(shown)} of {len(flaky)} flaky tests.</p>'
            if len(flaky) > len(shown)
            else ""
        )
        flaky_section = f"""
<section id="flaky">
  <h2>Flaky ranking <span class="dim">— all history, by flip count &times; avg duration</span></h2>
  {note}
  <table class="data-table">
    <thead><tr><th>Test</th><th>Flips</th><th>Avg duration</th><th>Score</th><th>Attempts</th></tr></thead>
    <tbody>{flaky_rows}</tbody>
  </table>
</section>"""
    else:
        flaky_section = """
<section id="flaky">
  <h2>Flaky ranking <span class="dim">— all history, by flip count &times; avg duration</span></h2>
  <p class="empty">No test has both passed and failed across history yet — nothing flaky on record.</p>
</section>"""

    # ---- slowest tests ----
    if slowest:
        slow_rows = "".join(
            f'<tr data-marker="" data-area="{r["area"]}" data-outcome="">'
            f'<td class="mono nodeid">{html.escape(r["nodeid"])}</td>'
            f'<td>{fmt_duration(r["recent_duration"])}</td>'
            f'<td>{fmt_duration(r["median_duration"])}</td>'
            f'<td>{_trend_arrow(r["trend"])}</td>'
            f'<td>{r["samples"]}</td>'
            f"</tr>"
            for r in slowest
        )
        slowest_section = f"""
<section id="slowest">
  <h2>Slowest tests <span class="dim">— top {len(slowest)}, most recent run</span></h2>
  <table class="data-table">
    <thead><tr><th>Test</th><th>Recent</th><th>Historical median</th><th>Trend</th><th>Samples</th></tr></thead>
    <tbody>{slow_rows}</tbody>
  </table>
</section>"""
    else:
        slowest_section = """
<section id="slowest">
  <h2>Slowest tests</h2>
  <p class="empty">No timed tests yet.</p>
</section>"""

    # ---- this run's failures ----
    if failures:
        fail_rows = []
        for f in failures:
            shot = (
                f'<a href="{html.escape(f["screenshot"])}" target="_blank">screenshot</a>'
                if f["screenshot"]
                else '<span class="dim">no screenshot</span>'
            )
            fail_rows.append(
                f'<details class="fail-row" data-marker="{html.escape(f["marker"])}" '
                f'data-area="{f["area"]}" data-outcome="{f["outcome"]}">'
                f'<summary><span class="badge bad">{f["outcome"].upper()}</span> '
                f'<span class="mono nodeid">{html.escape(f["nodeid"])}</span> '
                f'<span class="dim">{fmt_duration(f["duration"])}</span></summary>'
                f'<pre class="fail-msg">{html.escape(f["failure_message"])}</pre>'
                f'<p>{shot}</p>'
                f"</details>"
            )
        failures_section = f"""
<section id="failures">
  <h2>This run's failures <span class="dim">— {len(failures)}</span></h2>
  {''.join(fail_rows)}
</section>"""
    else:
        failures_section = """
<section id="failures">
  <h2>This run's failures</h2>
  <p class="empty ok-text">None — latest run had no failures or errors.</p>
</section>"""

    # ---- filters toolbar ----
    marker_opts = "".join(f'<option value="{html.escape(m)}">{html.escape(m)}</option>' for m in all_markers)
    area_opts = "".join(f'<option value="{a}">{a.upper()}</option>' for a in all_areas)
    filters_section = f"""
<div class="filters" id="filters">
  <span class="filters-label">Filter:</span>
  <label>Marker
    <select id="f-marker" onchange="applyFilters()">
      <option value="">All</option>
      {marker_opts}
    </select>
  </label>
  <label>Area
    <select id="f-area" onchange="applyFilters()">
      <option value="">All</option>
      {area_opts}
    </select>
  </label>
  <label>Outcome
    <select id="f-outcome" onchange="applyFilters()">
      <option value="">All</option>
      <option value="pass">Pass</option>
      <option value="fail">Fail</option>
      <option value="error">Error</option>
      <option value="skip">Skip</option>
    </select>
  </label>
  <button type="button" onclick="clearFilters()">Clear</button>
  <span class="dim" id="filter-count"></span>
</div>"""

    generated_note = f'<p class="dim footer-note">Built from {len(runs)} run{"s" if len(runs) != 1 else ""} in {html.escape(str(history_dir))}. Static file — safe to open via file://.</p>'

    return HTML_SHELL.format(
        header=header,
        filters=filters_section,
        trend=trend_section,
        stability=stability_section,
        flaky=flaky_section,
        slowest=slowest_section,
        failures=failures_section,
        footer=generated_note,
    )


HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Netropy UI test results</title>
<style>
  :root {{
    --bg: #f5f7f6; --surface: #ffffff; --surface-2: #edf1ef;
    --ink: #161a1d; --ink-dim: #5b6670; --rule: #dbe1df;
    --accent: #1f3a5f; --ok: #1e7145; --ok-bg: #e5f3ec;
    --bad: #b23a2e; --bad-bg: #fbeae8; --warn: #9c6b14; --warn-bg: #faf1e1;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #11161a; --surface: #171e24; --surface-2: #1e262d;
      --ink: #e7ecee; --ink-dim: #93a3ac; --rule: #2b363e;
      --accent: #8fb4de; --ok: #4cc38a; --ok-bg: #16281f;
      --bad: #e2685a; --bad-bg: #34201d; --warn: #d9a441; --warn-bg: #332711;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--ink); margin: 0;
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5;
  }}
  .page {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 80px; }}
  .mono {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
  h1 {{ font-size: 26px; margin: 0; }}
  h2 {{ font-size: 16px; margin: 0 0 12px; }}
  h3 {{ font-size: 13px; margin: 0 0 6px; color: var(--ink-dim); font-weight: 600; }}
  .dim {{ color: var(--ink-dim); font-size: 13px; }}
  .sep {{ color: var(--ink-dim); margin: 0 4px; }}
  section {{ margin: 36px 0; }}
  .empty {{ color: var(--ink-dim); padding: 12px 0; }}
  .ok-text {{ color: var(--ok); }}

  .header-grid {{ display: flex; gap: 20px; align-items: center; padding: 18px 0; border-bottom: 1px solid var(--rule); }}
  .status-badge {{
    flex: none; width: 96px; height: 96px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: 800; letter-spacing: 0.03em;
  }}
  .status-badge.ok {{ background: var(--ok-bg); color: var(--ok); }}
  .status-badge.bad {{ background: var(--bad-bg); color: var(--bad); }}
  .run-line {{ font-size: 15px; margin-bottom: 4px; }}
  .run-stats {{ margin-top: 8px; font-size: 14px; }}
  .pill {{
    background: var(--surface-2); border: 1px solid var(--rule); border-radius: 100px;
    padding: 1px 10px; font-size: 12px; font-family: ui-monospace, monospace;
  }}

  .filters {{
    display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
    background: var(--surface); border: 1px solid var(--rule); border-radius: 10px;
    padding: 10px 14px; margin: 20px 0 0; position: sticky; top: 8px; z-index: 5;
  }}
  .filters-label {{ font-weight: 600; font-size: 13px; }}
  .filters label {{ font-size: 13px; display: flex; gap: 6px; align-items: center; }}
  .filters select, .filters button {{
    font-size: 13px; padding: 3px 6px; border-radius: 6px; border: 1px solid var(--rule);
    background: var(--surface-2); color: var(--ink);
  }}
  .filters button {{ cursor: pointer; }}

  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 14px; }}
  svg.chart {{ display: block; }}
  .grid {{ stroke: var(--rule); stroke-width: 1; }}
  .axis {{ fill: var(--ink-dim); font-size: 10px; }}
  .line {{ fill: none; stroke-width: 2; }}
  .area {{ opacity: 0.12; }}
  .pt {{ fill: var(--surface); stroke: var(--ink-dim); stroke-width: 1.5; }}
  .pt:hover {{ stroke: var(--accent); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th {{
    text-align: left; font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase;
    color: var(--ink-dim); border-bottom: 1px solid var(--rule); padding: 6px 10px 8px 0;
  }}
  td {{ padding: 8px 10px 8px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  .nodeid {{ word-break: break-all; }}
  .badge {{
    display: inline-block; font-size: 10.5px; font-weight: 700; padding: 2px 7px;
    border-radius: 100px; letter-spacing: 0.03em;
  }}
  .badge.bad {{ background: var(--bad-bg); color: var(--bad); }}
  .flaky-row {{ background: var(--bad-bg); }}
  .spark-cell {{ font-family: ui-monospace, monospace; letter-spacing: 1px; }}
  .spark.ok {{ color: var(--ok); }}
  .spark.bad {{ color: var(--bad); font-weight: 700; }}
  .spark.skip {{ color: var(--ink-dim); }}
  .arrow.up {{ color: var(--bad); }}
  .arrow.down {{ color: var(--ok); }}
  .arrow.flat {{ color: var(--ink-dim); }}

  .session-picker {{ display: block; margin-bottom: 12px; font-size: 13px; }}
  .session-picker select {{ margin-left: 6px; padding: 3px 6px; border-radius: 6px; border: 1px solid var(--rule); background: var(--surface); color: var(--ink); }}

  details.fail-row {{
    background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
    padding: 8px 12px; margin-bottom: 8px;
  }}
  details.fail-row summary {{ cursor: pointer; display: flex; gap: 10px; align-items: baseline; }}
  .fail-msg {{
    white-space: pre-wrap; background: var(--surface-2); border-radius: 6px; padding: 10px;
    margin: 10px 0; font-size: 12.5px; max-height: 300px; overflow: auto;
  }}

  .footer-note {{ margin-top: 40px; border-top: 1px solid var(--rule); padding-top: 14px; }}

  [hidden] {{ display: none !important; }}

  @media (max-width: 720px) {{
    .chart-grid {{ grid-template-columns: 1fr; }}
    .header-grid {{ flex-direction: column; align-items: flex-start; }}
  }}
</style>
</head>
<body>
<div class="page">
  <div id="header-root">{header}</div>
  {filters}
  {trend}
  {stability}
  {flaky}
  {slowest}
  {failures}
  {footer}
</div>
<script>
  function showSession(idx) {{
    document.querySelectorAll('.session-block').forEach(function(el) {{
      el.style.display = (el.dataset.sessionIndex === String(idx)) ? '' : 'none';
    }});
  }}

  function applyFilters() {{
    var marker = document.getElementById('f-marker').value;
    var area = document.getElementById('f-area').value;
    var outcome = document.getElementById('f-outcome').value;
    var rows = document.querySelectorAll('tr[data-area], details[data-area]');
    var shown = 0, total = 0;
    rows.forEach(function(row) {{
      total++;
      var ok = true;
      if (marker && row.dataset.marker !== marker) ok = false;
      if (area && row.dataset.area !== area) ok = false;
      if (outcome && row.dataset.outcome !== outcome) ok = false;
      row.hidden = !ok;
      if (ok) shown++;
    }});
    var counter = document.getElementById('filter-count');
    if (counter) {{
      counter.textContent = (marker || area || outcome) ? (shown + ' / ' + total + ' rows shown') : '';
    }}
  }}

  function clearFilters() {{
    ['f-marker', 'f-area', 'f-outcome'].forEach(function(id) {{
      var el = document.getElementById(id);
      if (el) el.value = '';
    }});
    applyFilters();
  }}
</script>
</body>
</html>
"""


def build(history_dir: Path = DEFAULT_HISTORY_DIR, out_path: Path = DEFAULT_OUT) -> Path:
    runs = load_all_runs(history_dir)
    html_text = render_html(runs, history_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text)
    return out_path


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = build(args.history_dir, args.out)
    print(f"build_report: wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
