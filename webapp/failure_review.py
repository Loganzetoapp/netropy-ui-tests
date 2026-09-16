"""Logs dashboard-triggered test failures into netropy-ui-findings.md.

Two modes, chosen automatically by whether the caller has enabled
automatic review (see `runner.TestRunner.enable_failure_review`):

- **No API key (default):** `queue_pending_review` writes the failure's
  raw evidence (trace summary, screenshot/trace links) into a "pending
  review" section — no API call, no cost, always on. Reviewing those —
  reading the trace/screenshot, writing an actual finding, promoting it
  to "Confirmed product issues" or ruling it out — happens later in a
  Claude Code session.
- **`ANTHROPIC_API_KEY` set:** `review_failure` sends that same evidence
  (screenshot + trace summary) to Claude directly, and
  `append_reviewed_finding` writes the resulting evidence-grounded finding
  straight into its own section — no Claude Code session needed. This is
  what makes unattended/remote-hosted deployments usable: nobody has to be
  around interactively reviewing the queue for findings to accumulate.

Everything here is best-effort: a failure in this module must never break
test-run reporting (see the try/except around its call site in runner.py,
which also falls back to the raw pending-review queue if the API call
itself fails — a bad key or network error shouldn't lose the evidence).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from webapp.trace_summary import extract_trace_summary as _extract_trace_summary

FINDINGS_SECTION_HEADER = "## Dashboard failures — pending review"
AUTO_REVIEW_SECTION_HEADER = "## Dashboard failure reviews (automatic)"
REVIEW_MODEL = "claude-haiku-4-5"
REVIEW_MAX_TOKENS = 800


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


def _load_screenshot_block(screenshot_path: Path) -> Optional[dict]:
    try:
        data = screenshot_path.read_bytes()
    except OSError:
        return None
    media_type = "image/png" if screenshot_path.suffix.lower() == ".png" else "image/jpeg"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(data).decode("ascii"),
        },
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
    API key or network access to be tested. Raises on any API error —
    callers (see runner.py) catch and fall back to the raw pending-review
    queue rather than losing the evidence."""
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
        model=REVIEW_MODEL,
        max_tokens=REVIEW_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def append_reviewed_finding(
    findings_path: Path,
    nodeid: str,
    review_text: str,
    screenshot_rel: Optional[str],
    trace_rel: Optional[str],
) -> None:
    """Append one Claude-written review to netropy-ui-findings.md —
    append-only, so a human editing the file at the same time never has
    their edits overwritten. Kept in its own section, never mixed into
    "Confirmed product issues": this is one automated single-run read, not
    a human/session-reproduced, confirmed bug. Creates the section header
    (with that distinction stated up front) the first time this is
    called."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry_lines = [f"### {timestamp} — {nodeid}", "", review_text.strip(), ""]
    if screenshot_rel:
        entry_lines.append(f"Screenshot: `{screenshot_rel}`")
    if trace_rel:
        entry_lines.append(f"Trace: `{trace_rel}`")
    entry_lines.append("")
    entry = "\n".join(entry_lines)

    existing = findings_path.read_text() if findings_path.exists() else ""
    if AUTO_REVIEW_SECTION_HEADER not in existing:
        preamble = (
            "\nAutomatically written by Claude the moment a dashboard-triggered "
            "test fails — each entry reflects one run's evidence, not an "
            "independently reproduced/confirmed bug like the section above. "
            "Worth a human glance before fully trusting one, same as any "
            "single-run read.\n\n"
        )
        block = f"\n{AUTO_REVIEW_SECTION_HEADER}\n{preamble}{entry}"
    else:
        block = f"\n{entry}"

    with findings_path.open("a") as f:
        f.write(block)
