"""Automated Claude review of dashboard-triggered test failures.

When a webapp-triggered run fails, this pulls the evidence already being
captured for the Results page (the failure screenshot, the Playwright
trace) into a form an LLM can read, asks Claude to write a short,
evidence-grounded finding, and appends it to netropy-ui-findings.md.

Disabled by default — only active once webapp/app.py's __main__ block
finds ANTHROPIC_API_KEY in .env and calls TestRunner.enable_failure_review.
Everything here is best-effort: a failure in this module must never break
test-run reporting (see the try/except around its call site in runner.py).
"""
from __future__ import annotations

import base64
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MODEL = "claude-sonnet-5"
MAX_TRACE_SUMMARY_CHARS = 8000
FINDINGS_SECTION_HEADER = "## Dashboard failure reviews"


def _extract_trace_summary(trace_zip_path: Path) -> str:
    """Boil a Playwright trace.zip down to the same kind of evidence a
    human would pull out in the trace viewer: the action sequence (with
    pass/fail per step), any JS/console errors, and any non-2xx network
    responses — compact enough to hand to an LLM alongside the failure
    screenshot instead of the whole (often multi-MB, partly binary) zip."""
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


def _load_screenshot_block(screenshot_path: Path) -> Optional[dict]:
    try:
        data = screenshot_path.read_bytes()
    except OSError:
        return None
    media_type = "image/png" if screenshot_path.suffix.lower() == ".png" else "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode("ascii")},
    }


REVIEW_PROMPT = """You are reviewing a failed automated UI test run against the Netropy \
Traffic Generator web interface, for an internal findings log. Below is the \
test that failed, its failure message, and a compact summary extracted from \
its Playwright trace (action sequence, JS/console errors, any non-2xx \
network responses). A screenshot taken at the moment of failure may also be \
attached.

Test: {nodeid}
Failure message: {detail}

Trace summary:
{trace_summary}

Write a short, evidence-grounded finding (3-6 sentences) for the findings \
log. Cite specific evidence — exact status codes, exact error text, exact \
actions — rather than vague summaries. State plainly whether this looks \
like a real product bug, a test/selector issue, or is inconclusive from \
this one run, and say what evidence supports that read. This is a single \
run, not a reproduced/confirmed issue — say what the evidence does and \
doesn't show rather than declaring something "confirmed". Do not add a \
heading or restate the test name — write only the finding text."""


def review_failure(
    nodeid: str,
    detail: Optional[str],
    screenshot_path: Optional[Path],
    trace_path: Optional[Path],
    client,
) -> str:
    """Ask Claude to write an evidence-grounded finding for one failed
    iteration. `client` is an injected Anthropic-SDK-shaped object (an
    `anthropic.Anthropic(...)` instance in production, a fake with a
    matching `.messages.create(...)` in tests) so this never needs a real
    API key or network access to be tested."""
    trace_summary = _extract_trace_summary(trace_path) if trace_path else "(no trace captured)"
    content: list[dict] = [
        {
            "type": "text",
            "text": REVIEW_PROMPT.format(
                nodeid=nodeid, detail=detail or "(none)", trace_summary=trace_summary
            ),
        }
    ]
    if screenshot_path:
        image_block = _load_screenshot_block(screenshot_path)
        if image_block:
            content.append(image_block)

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def append_finding(
    findings_path: Path,
    nodeid: str,
    review_text: str,
    screenshot_rel: Optional[str],
    trace_rel: Optional[str],
) -> None:
    """Append one automated review to netropy-ui-findings.md — append-only,
    so a human editing the file at the same time never has their edits
    overwritten. Creates the section header (with a note distinguishing
    these from the manually-reproduced/confirmed section above) the first
    time this is called."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry_lines = [f"### {timestamp} — {nodeid}", "", review_text.strip(), ""]
    if screenshot_rel:
        entry_lines.append(f"Screenshot: `{screenshot_rel}`")
    if trace_rel:
        entry_lines.append(f"Trace: `{trace_rel}`")
    entry_lines.append("")
    entry = "\n".join(entry_lines)

    existing = findings_path.read_text() if findings_path.exists() else ""
    if FINDINGS_SECTION_HEADER not in existing:
        preamble = (
            "\nAutomatically generated by Claude when a test fails through the "
            "dashboard — each entry reflects one run's evidence, not an "
            "independently reproduced/confirmed bug like the section above.\n\n"
        )
        block = f"\n{FINDINGS_SECTION_HEADER}\n{preamble}{entry}"
    else:
        block = f"\n{entry}"

    with findings_path.open("a") as f:
        f.write(block)
