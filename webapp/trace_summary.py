"""Boils a Playwright trace.zip down to compact, embeddable evidence: the
action sequence (with pass/fail per step), any JS/console errors, and any
non-2xx network responses — the same kind of thing a human would pull out
in the trace viewer, without linking to the (often multi-MB, partly
binary) zip itself.

Factored out of `webapp/failure_review.py` (which writes this into the
findings doc's pending-review queue) so a later run-detail endpoint can
reuse the exact same trace parsing rather than duplicating it.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

MAX_TRACE_SUMMARY_CHARS = 8000


def extract_trace_summary(trace_zip_path: Path) -> str:
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
