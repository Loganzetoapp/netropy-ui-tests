"""Tests for the lightweight known-issue keyword matcher. Deliberately
uses a small temp fixture findings doc rather than the real, ~300-line
netropy-ui-findings.md — real content changes over time and this suite
must stay hermetic. Run with:
    pytest --confcutdir=webapp webapp/tests/test_known_issues.py -v
"""
from webapp.known_issues import match_failure, parse_confirmed_issues

FIXTURE_FINDINGS = """# Findings

## Confirmed product issues

### Testbed activation returns 502 Bad Gateway for long names
Activation of a testbed fails with a 502 Bad Gateway response when the
testbed name is too long. Confirmed on T10 lifecycle tests during
activation.
— tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py

### Copy UID button does nothing
The copy-to-clipboard control silently fails because the page is served
over plain HTTP, so navigator.clipboard is unavailable. No T-number
mentioned here.

## Where the written test plan didn't match the product

### Something unrelated
This section must not be parsed as a confirmed issue.
"""


def test_parse_confirmed_issues_extracts_titles_and_bodies(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    issues = parse_confirmed_issues(findings)
    titles = [i["title"] for i in issues]
    assert titles == [
        "Testbed activation returns 502 Bad Gateway for long names",
        "Copy UID button does nothing",
    ]
    assert "Something unrelated" not in titles
    assert "Bad Gateway" in issues[0]["body"]


def test_parse_confirmed_issues_infers_area_from_t_number(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    by_title = {i["title"]: i for i in parse_confirmed_issues(findings)}
    assert by_title["Testbed activation returns 502 Bad Gateway for long names"]["area"] == "T10"
    assert by_title["Copy UID button does nothing"]["area"] is None


def test_parse_confirmed_issues_returns_empty_for_missing_file(tmp_path):
    assert parse_confirmed_issues(tmp_path / "does-not-exist.md") == []


def test_parse_confirmed_issues_returns_empty_when_section_missing(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text("# Findings\n\nNo confirmed section here.\n")
    assert parse_confirmed_issues(findings) == []


def test_match_failure_finds_relevant_known_issue(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    matches = match_failure(
        "tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py"
        "::test_t10_default_addressing_activation",
        "502 Bad Gateway activation failed for testbed name",
        "T10",
        findings,
    )
    assert matches
    assert matches[0]["title"] == "Testbed activation returns 502 Bad Gateway for long names"
    assert matches[0]["label"] == "possible match — review"
    assert matches[0]["score"] > 0
    assert len(matches) <= 3


def test_match_failure_returns_empty_when_nothing_relevant(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    matches = match_failure(
        "tests/t3_x/test_something_totally_different.py::test_something_totally_different",
        "assertion failed comparing widget colors",
        None,
        findings,
    )
    assert matches == []


def test_match_failure_requires_keyword_overlap_not_just_area(tmp_path):
    """An area match alone, with zero shared keywords, must not be enough
    to surface a "possible match" — that would be noise, not signal."""
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    matches = match_failure(
        "tests/t10_t12_lifecycle/test_totally_unrelated_thing.py::test_totally_unrelated_thing",
        "some completely unrelated failure about colors",
        "T10",
        findings,
    )
    assert matches == []


def test_match_failure_caps_at_three_matches(tmp_path):
    entries = "\n\n".join(
        f"### Widget rendering issue variant {i}\n"
        "The widget rendering pipeline breaks, causing a widget rendering failure."
        for i in range(5)
    )
    findings = tmp_path / "findings.md"
    findings.write_text(f"# Findings\n\n## Confirmed product issues\n\n{entries}\n")
    matches = match_failure(
        "tests/x.py::test_widget_rendering",
        "widget rendering failure observed during widget rendering",
        None,
        findings,
    )
    assert 1 <= len(matches) <= 3


def test_match_failure_never_raises_on_missing_findings_file(tmp_path):
    assert match_failure("tests/x.py::test_x", "boom", None, tmp_path / "missing.md") == []


def test_match_failure_handles_no_failure_message(tmp_path):
    """A crash/error iteration with no failure_message text at all — only
    the test name to go on — must not raise, and may legitimately find
    nothing."""
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    matches = match_failure("tests/x.py::test_x", None, None, findings)
    assert matches == []
