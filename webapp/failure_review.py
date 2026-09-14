"""Logs dashboard-triggered test failures into netropy-ui-findings.md for
later review — no API call, no API key. When a webapp-triggered run fails,
the failure's evidence (a summary extracted from its Playwright trace:
action sequence, JS/console errors, non-2xx network responses) is written
straight into a "pending review" section of the findings doc. Reviewing
those — reading the trace/screenshot, writing an actual finding, promoting
it to "Confirmed product issues" or ruling it out — happens later in a
Claude Code session (ask Claude to review the pending entries), not here.

Everything here is best-effort: a failure in this module must never break
test-run reporting (see the try/except around its call site in runner.py).
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MAX_TRACE_SUMMARY_CHARS = 8000
FINDINGS_SECTION_HEADER = "## Dashboard failures — pending review"


def _extract_trace_summary(trace_zip_path: Path) -> str:
    """Boil a Playwright trace.zip down to the same kind of evidence a
    human would pull out in the trace viewer: the action sequence (with
    pass/fail per step), any JS/console errors, and any non-2xx network
    responses — compact enough to embed directly in the findings doc
    instead of just linking to the (often multi-MB, partly binary) zip."""
    lines: list[str] = []
    try:
        with zipfile.ZipFile(trace_zip_path) as zf:
            names = zf.namelist()
            trace_name = next((n for n in names if n.endswith("trace.trace")), None)
            network_name = next((n for n in names if n.endswith("trace.network")), None)

            if trace_name:
                actions: dict[str, dict] = {}
                order: list[str] = []
                for raw in zf.read(trace_name).decode("utf-8").splitlines():
                    if not raw.strip():
                        continue
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    t = ev.get("type")
                    if t == "before":
                        call_id = ev["callId"]
                        actions[call_id] = {
                            "label": f"{ev.get('class')}.{ev.get('method')}({ev.get('params')})"
                        }
                        order.append(call_id)
                    elif t == "after":
                        call_id = ev.get("callId")
                        if call_id in actions and ev.get("error"):
                            actions[call_id]["error"] = ev["error"]
                    elif t == "event" and ev.get("method") == "pageError":
                        msg = (
                            ev.get("params", {})
                            .get("error", {})
                            .get("error", {})
                            .get("message")
                        )
                        if msg:
                            lines.append(f"Page error (JS exception): {msg}")
                    elif t == "console" and ev.get("messageType") == "error":
                        lines.append(f"Console error: {ev.get('text')}")

                if order:
                    lines.append("Action sequence:")
                    for call_id in order:
                        a = actions[call_id]
                        marker = f"  FAILED: {a['error']['message']}" if a.get("error") else ""
                        lines.append(f"  {a['label']}{marker}")

            if network_name:
                failing = []
                for raw in zf.read(network_name).decode("utf-8").splitlines():
                    if not raw.strip():
                        continue
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    snap = ev.get("snapshot", {})
                    resp = snap.get("response", {})
                    status = resp.get("status")
                    if isinstance(status, int) and status >= 400:
                        req = snap.get("request", {})
                        failing.append(
                            f"{req.get('method')} {req.get('url')} -> "
                            f"{status} {resp.get('statusText')}"
                        )
                if failing:
                    lines.append("")
                    lines.append("Non-2xx network responses:")
                    lines.extend(f"  {f}" for f in failing)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        return f"(trace could not be read: {exc})"

    text = "\n".join(lines)
    if len(text) > MAX_TRACE_SUMMARY_CHARS:
        text = text[:MAX_TRACE_SUMMARY_CHARS] + "\n...(truncated)"
    return text or "(no notable events found in trace)"


def _escape_markdown_text(text: str) -> str:
    """Neutralize `<`/`>`/`&` in dynamic, product/test-generated text
    before it's embedded in the findings doc — this file gets rendered to
    HTML for the dashboard's Findings page (see app.py's /api/findings),
    and unlike the rest of the doc (hand-written by a person), this text
    comes from pytest failure messages and trace content, which could in
    principle contain something that reads as markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def queue_pending_review(
    findings_path: Path,
    nodeid: str,
    detail: Optional[str],
    screenshot_rel: Optional[str],
    trace_rel: Optional[str],
    trace_path: Optional[Path],
) -> None:
    """Append one failed iteration to netropy-ui-findings.md's pending-
    review queue. Append-only, so a human editing the file at the same
    time never has their edits overwritten. Creates the section header
    (with a note on how these differ from the confirmed section above)
    the first time this is called."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    trace_summary = _extract_trace_summary(trace_path) if trace_path else "(no trace captured)"

    entry_lines = [
        f"### {timestamp} — {nodeid}",
        "",
        "**Status:** pending review",
        "",
        f"Failure message: {_escape_markdown_text(detail) if detail else '(none)'}",
        "",
        "Trace summary:",
        "```",
        # Not escaped: this is going inside a fenced code block, which the
        # markdown renderer already HTML-escapes on its own when producing
        # <pre><code> — escaping it here too would corrupt the raw .md
        # file for anyone reading it directly (e.g. "->" becoming "-&gt;").
        trace_summary,
        "```",
    ]
    if screenshot_rel:
        entry_lines.append(f"Screenshot: `{screenshot_rel}`")
    if trace_rel:
        entry_lines.append(f"Trace: `{trace_rel}`")
    entry_lines.append("")
    entry = "\n".join(entry_lines)

    existing = findings_path.read_text() if findings_path.exists() else ""
    if FINDINGS_SECTION_HEADER not in existing:
        preamble = (
            "\nLogged automatically when a test fails through the dashboard — "
            "each entry is one run's raw evidence, not yet reviewed. Ask Claude "
            "to review the pending entries in a session: it reads the trace/"
            "screenshot and either promotes a real one to \"Confirmed product "
            "issues\" above, or notes why it isn't (test/selector issue, "
            "inconclusive, etc.), then marks the entry reviewed.\n\n"
        )
        block = f"\n{FINDINGS_SECTION_HEADER}\n{preamble}{entry}"
    else:
        block = f"\n{entry}"

    with findings_path.open("a") as f:
        f.write(block)
