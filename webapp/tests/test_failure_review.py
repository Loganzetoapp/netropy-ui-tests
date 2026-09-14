"""Tests for the dashboard-failure pending-review queue. No API calls, no
network access — this only ever writes to netropy-ui-findings.md. Run
with: pytest --confcutdir=webapp webapp/tests/test_failure_review.py -v
"""
import json
import zipfile

from webapp.failure_review import (
    FINDINGS_SECTION_HEADER,
    _extract_trace_summary,
    queue_pending_review,
)


def _write_real_shaped_trace_zip(path, include_network_error=True):
    """A minimal trace.zip using the same event shapes seen in a real
    Playwright trace (before/after with an Expect failure, a pageError
    event, a console error, plus a resource-snapshot with a 403) — small
    enough to hand-write, realistic enough to exercise the real parser."""
    trace_events = [
        {
            "type": "before",
            "callId": "call@1",
            "class": "Frame",
            "method": "click",
            "params": {"selector": "internal:role=button[name=\"Release\"i]"},
        },
        {"type": "after", "callId": "call@1"},
        {
            "type": "before",
            "callId": "call@2",
            "class": "Frame",
            "method": "expect",
            "params": {"selector": "internal:text=\"Available\"s"},
        },
        {
            "type": "after",
            "callId": "call@2",
            "error": {"name": "Expect", "message": "Expect failed"},
        },
        {
            "type": "event",
            "method": "pageError",
            "params": {"error": {"error": {"message": "SecurityError: blocked"}}},
        },
        {"type": "console", "messageType": "error", "text": "Failed to load resource: 403"},
    ]
    trace_lines = "\n".join(json.dumps(e) for e in trace_events)

    network_lines = ""
    if include_network_error:
        network_events = [
            {
                "snapshot": {
                    "request": {"method": "POST", "url": "http://box/ports/1/release"},
                    "response": {"status": 403, "statusText": "Forbidden"},
                }
            },
            {
                "snapshot": {
                    "request": {"method": "GET", "url": "http://box/"},
                    "response": {"status": 200, "statusText": "OK"},
                }
            },
        ]
        network_lines = "\n".join(json.dumps(e) for e in network_events)

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("trace.trace", trace_lines)
        zf.writestr("trace.network", network_lines)


def test_extract_trace_summary_includes_action_sequence_and_failure(tmp_path):
    trace_zip = tmp_path / "trace.zip"
    _write_real_shaped_trace_zip(trace_zip)
    summary = _extract_trace_summary(trace_zip)
    assert "Frame.click" in summary
    assert "Frame.expect" in summary
    assert "FAILED: Expect failed" in summary


def test_extract_trace_summary_includes_page_and_console_errors(tmp_path):
    trace_zip = tmp_path / "trace.zip"
    _write_real_shaped_trace_zip(trace_zip)
    summary = _extract_trace_summary(trace_zip)
    assert "Page error (JS exception): SecurityError: blocked" in summary
    assert "Console error: Failed to load resource: 403" in summary


def test_extract_trace_summary_includes_non_2xx_network_responses(tmp_path):
    trace_zip = tmp_path / "trace.zip"
    _write_real_shaped_trace_zip(trace_zip)
    summary = _extract_trace_summary(trace_zip)
    assert "POST http://box/ports/1/release -> 403 Forbidden" in summary
    # the 200 response must not be listed as a failure
    assert "GET http://box/ -> 200" not in summary


def test_extract_trace_summary_handles_missing_file_gracefully(tmp_path):
    summary = _extract_trace_summary(tmp_path / "does-not-exist.zip")
    assert "could not be read" in summary


def test_extract_trace_summary_handles_corrupt_zip_gracefully(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip file")
    summary = _extract_trace_summary(bad_zip)
    assert "could not be read" in summary


def test_queue_pending_review_creates_section_header_once(tmp_path):
    findings = tmp_path / "netropy-ui-findings.md"
    findings.write_text("# Findings\n\n## Confirmed product issues\n\nSomething real.\n")
    trace_zip = tmp_path / "trace.zip"
    _write_real_shaped_trace_zip(trace_zip)

    queue_pending_review(
        findings, "tests/a.py::test_a", "boom", "shot1.png", "trace1.zip", trace_zip
    )
    queue_pending_review(findings, "tests/b.py::test_b", None, None, None, None)

    content = findings.read_text()
    assert content.count(FINDINGS_SECTION_HEADER) == 1
    assert "tests/a.py::test_a" in content
    assert "tests/b.py::test_b" in content
    assert "Failure message: boom" in content
    assert "Screenshot: `shot1.png`" in content
    assert "Trace: `trace1.zip`" in content
    assert "**Status:** pending review" in content
    # the real trace evidence must be embedded, not just linked
    assert "POST http://box/ports/1/release -> 403 Forbidden" in content
    # pre-existing content must survive untouched
    assert "## Confirmed product issues" in content
    assert "Something real." in content


def test_queue_pending_review_creates_file_if_missing(tmp_path):
    findings = tmp_path / "netropy-ui-findings.md"
    queue_pending_review(findings, "tests/a.py::test_a", "boom", None, None, None)
    assert findings.exists()
    assert "tests/a.py::test_a" in findings.read_text()


def test_queue_pending_review_escapes_html_like_content(tmp_path):
    """Dynamic content (failure messages, trace text) ends up rendered as
    HTML on the dashboard's Findings page (see app.py's /api/findings) —
    anything that looks like a tag must render as visible text there, not
    get interpreted as markup."""
    findings = tmp_path / "netropy-ui-findings.md"
    queue_pending_review(
        findings, "tests/a.py::test_a", "<script>alert(1)</script>", None, None, None
    )
    content = findings.read_text()
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_queue_pending_review_handles_no_trace_captured(tmp_path):
    findings = tmp_path / "netropy-ui-findings.md"
    queue_pending_review(findings, "tests/a.py::test_a", "boom", None, None, None)
    assert "(no trace captured)" in findings.read_text()
