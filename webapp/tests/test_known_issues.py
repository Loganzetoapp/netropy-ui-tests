"""Tests for the lightweight known-issue keyword matcher. Deliberately
uses a small temp fixture findings doc rather than the real, ~300-line
netropy-ui-findings.md — real content changes over time and this suite
must stay hermetic. Run with:
    pytest --confcutdir=webapp webapp/tests/test_known_issues.py -v
"""
from webapp.known_issues import (
    STATUS_FIXED,
    STATUS_INVESTIGATING,
    STATUS_OPEN,
    _infer_area,
    classify_status,
    match_failure,
    parse_confirmed_issues,
)

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


def test_infer_area_matches_lowercase_filepath_style_references():
    """Newer findings reference an area only through a test file path or
    nodeid, never a standalone "T10" word — e.g. "reproduced in
    tests/t10_t12_lifecycle/test_t10_clone_while_active.py". Underscore is
    a \\w char, so \\b never fires between "_" and "t10" here; this must
    still resolve to T10, not None."""
    assert _infer_area(
        "Reproduced via `tests/t10_t12_lifecycle/test_t10_clone_while_active.py`."
    ) == "T10"
    assert _infer_area(
        "See test_t10_unrelated_action_during_live_run for the boundary case."
    ) == "T10"
    assert _infer_area("No area reference here at all.") is None


def test_parse_confirmed_issues_defaults_status_to_open_when_no_status_line(tmp_path):
    """Neither fixture entry has an explicit "Status: ..." line — both
    must default to the least-resolved bucket rather than guessing."""
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    statuses = {i["title"]: i["status"] for i in parse_confirmed_issues(findings)}
    assert statuses["Testbed activation returns 502 Bad Gateway for long names"] == STATUS_OPEN
    assert statuses["Copy UID button does nothing"] == STATUS_OPEN


# --- classify_status ---------------------------------------------------------
#
# Fixture text below is written in the same register netropy-ui-findings.md's
# real "Status: ..." lines actually use (see that doc's "Confirmed product
# issues" section) — not synthetic keyword soup — so these tests double as
# a spec for the classifier's real-world behavior.


def test_classify_status_no_status_line_and_no_signal_defaults_to_open():
    body = (
        "The control produces no visible feedback at all. Root cause: a "
        "secure-context restriction in the browser. Fix options: serve "
        "over HTTPS, or add a fallback."
    )
    assert classify_status("Some bug does nothing", body) == STATUS_OPEN


def test_classify_status_plain_fixed_language():
    body = "Status: root cause identified and fixed in the latest build; verified with a clean re-run."
    assert classify_status("Some bug", body) == STATUS_FIXED


def test_classify_status_resolved_language():
    body = "Status: resolved after the backend patch; no longer reproduces."
    assert classify_status("Some bug", body) == STATUS_FIXED


def test_classify_status_intermittent_unresolved_is_investigating():
    body = "Status: intermittent, unresolved. Seen twice out of five attempts."
    assert classify_status("Some bug", body) == STATUS_INVESTIGATING


def test_classify_status_single_observation_not_yet_confirmed_is_investigating():
    body = (
        "Status: single observation only — flagging as a real anomaly "
        "worth a deliberate repro, not yet confirmed root cause."
    )
    assert classify_status("Some bug", body) == STATUS_INVESTIGATING


def test_classify_status_contested_fix_never_lands_in_fixed_bucket():
    """The exact shape of this repo's real 15-char-name-limit finding: a
    test-side workaround described as "fixed" sits right next to "the
    underlying product issue is still open" — the word "fixed" alone
    must never be enough to call the whole entry resolved."""
    body = (
        "Status: root cause confirmed and fixed test-side (every test now "
        "guards against it). The underlying product issue is still open, "
        "pending a fix from the vendor."
    )
    assert classify_status("Some bug", body) != STATUS_FIXED


def test_classify_status_falls_back_to_full_body_when_no_status_line():
    body = "This bug is completely unresolved and nobody has looked at it yet."
    assert classify_status("Some bug", body) == STATUS_INVESTIGATING


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


# --- strict mode (area-wide cross-referencing) -----------------------------
#
# strict=True is used only by the area-detail endpoint's cross-referencing
# loop (webapp/app.py). These tests prove: (1) the single-failure
# review-queue path (strict=False, the default) is completely unchanged —
# an area-bonus-plus-one-weak-word match still surfaces there, exactly as
# before; (2) strict mode requires real keyword-overlap contribution, not
# just the area bonus, so that same weak match is filtered out; (3) a
# genuinely rich, substantial overlap still surfaces under strict mode too
# — strict tightens the floor, it doesn't disable matching altogether.

STRICT_FIXTURE_FINDINGS = """# Findings

## Confirmed product issues

### Testbed activation returns 502 Bad Gateway for long names
Activation of a testbed fails with a 502 Bad Gateway response whenever
the testbed name is 16 characters or longer. Every activation attempt
for an over-length name returns 502 permanently, while a name of 15
characters or fewer activates cleanly every time. Confirmed on T10
lifecycle tests during activation. The wizard shows no error toast when
activation fails, leaving the Apply button stuck silently on the
addressing step.

### Port links drop after activation
Port links intermittently drop to No Link after activation on some
testbeds. Confirmed on T10 lifecycle hardware.
"""

STRICT_RICH_NODEID = (
    "tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py"
    "::test_t10_default_addressing_activation"
)
STRICT_RICH_MESSAGE = (
    "502 Bad Gateway returned during testbed activation for an "
    "over-length name; wizard Apply button stuck silently with no "
    "error toast"
)
STRICT_WEAK_NODEID = (
    "tests/t10_t12_lifecycle/test_t10_unrelated_widget_color.py"
    "::test_t10_unrelated_widget_color"
)
STRICT_WEAK_MESSAGE = "widget color assertion failed unexpectedly during rendering"


def test_match_failure_loose_mode_returns_weak_area_only_match(tmp_path):
    """Baseline: today's single-failure review-queue behavior (strict is
    False by default) still surfaces a match built almost entirely from
    the area bonus plus one or two incidental shared words — this is the
    exact noisy-but-acceptable-for-one-at-a-time-review case strict mode
    exists to filter out of the area-wide cross-referencing loop."""
    findings = tmp_path / "findings.md"
    findings.write_text(STRICT_FIXTURE_FINDINGS)
    matches = match_failure(STRICT_WEAK_NODEID, STRICT_WEAK_MESSAGE, "T10", findings)
    titles = {m["title"] for m in matches}
    assert "Testbed activation returns 502 Bad Gateway for long names" in titles


def test_match_failure_strict_mode_filters_out_weak_area_only_match(tmp_path):
    """The same weak match as above, requested with strict=True, must be
    filtered out — an area match plus a token or two of overlap is not
    "a real keyword-overlap contribution" under strict mode."""
    findings = tmp_path / "findings.md"
    findings.write_text(STRICT_FIXTURE_FINDINGS)
    matches = match_failure(
        STRICT_WEAK_NODEID, STRICT_WEAK_MESSAGE, "T10", findings, strict=True
    )
    assert matches == []


def test_match_failure_strict_mode_still_finds_genuinely_rich_match(tmp_path):
    """Strict mode tightens the floor, it doesn't disable matching: a
    failure that shares substantial real vocabulary with a finding (not
    just the area token and boilerplate) still surfaces under strict."""
    findings = tmp_path / "findings.md"
    findings.write_text(STRICT_FIXTURE_FINDINGS)
    matches = match_failure(
        STRICT_RICH_NODEID, STRICT_RICH_MESSAGE, "T10", findings, strict=True
    )
    assert matches
    assert matches[0]["title"] == "Testbed activation returns 502 Bad Gateway for long names"


def test_match_failure_strict_mode_ignores_bare_area_token_as_a_keyword(tmp_path):
    """A shared word that's just the area token spelled out ("t10") must
    not, on its own, count toward strict mode's keyword-overlap
    requirement — that would just be AREA_BONUS counting itself twice."""
    findings = tmp_path / "findings.md"
    findings.write_text(STRICT_FIXTURE_FINDINGS)
    matches = match_failure(
        "tests/t10_t12_lifecycle/test_t10_something_else.py::test_t10_something_else",
        "some completely unrelated failure about colors",
        "T10",
        findings,
        strict=True,
    )
    assert matches == []


def test_match_failure_handles_no_failure_message(tmp_path):
    """A crash/error iteration with no failure_message text at all — only
    the test name to go on — must not raise, and may legitimately find
    nothing."""
    findings = tmp_path / "findings.md"
    findings.write_text(FIXTURE_FINDINGS)
    matches = match_failure("tests/x.py::test_x", None, None, findings)
    assert matches == []
