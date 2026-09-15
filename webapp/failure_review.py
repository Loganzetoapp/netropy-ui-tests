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

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from webapp.trace_summary import extract_trace_summary as _extract_trace_summary

FINDINGS_SECTION_HEADER = "## Dashboard failures — pending review"


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
