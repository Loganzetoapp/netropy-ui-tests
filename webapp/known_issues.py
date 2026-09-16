"""Lightweight, non-authoritative correlation between a failed test run and
`netropy-ui-findings.md`'s "## Confirmed product issues" section.

Deliberately dumb: keyword/signature overlap, not ML (see the plan this
was built from — ReportPortal-style auto-analysis is overkill at this
repo's scale). Every match is surfaced as "possible match — review," never
auto-linked, mirroring the manual-link model the findings doc's own
"Dashboard failures — pending review" workflow already uses
(`webapp/failure_review.py`).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FINDINGS_PATH = REPO_ROOT / "netropy-ui-findings.md"

CONFIRMED_SECTION_HEADER = "## Confirmed product issues"
MATCH_LABEL = "possible match — review"

# Tuned, not principled: a shared token is worth 1 point; a matching area
# is worth a bit more than one shared token so it can tip a borderline
# match, but never carries a match on its own with zero keyword overlap.
AREA_BONUS = 1.5
MATCH_FLOOR = 1.5  # strictly greater than this to be returned
MAX_MATCHES = 3
MIN_TOKEN_LEN = 3

_AREA_TOKEN_RE = re.compile(r"\bT(\d{1,2})\b")
# Newer findings often reference an area only via a test file path or
# nodeid (`tests/t10_t12_lifecycle/test_t10_clone_while_active.py`), never
# spelling out "T10" as a standalone word — `_AREA_TOKEN_RE` alone misses
# these. Underscore is a \w character, so `\b` never fires between "_" and
# "t10" in "test_t10_..." — match on the literal "/" or "_" delimiter
# instead of relying on a word boundary there.
_AREA_FILEPATH_RE = re.compile(r"(?:^|[/_])[Tt](\d{1,2})_")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Common English stopwords plus a few words so generic to this suite
# (every failure message and every finding mentions them) that keeping
# them in would swamp real signal with noise.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "is", "are", "was", "were",
    "be", "been", "being", "to", "of", "in", "on", "at", "for", "with",
    "this", "that", "these", "those", "it", "its", "from", "by", "as",
    "not", "no", "does", "do", "did", "has", "have", "had", "into", "out",
    "over", "than", "then", "so", "very", "can", "could", "would", "should",
    "will", "shall", "about", "after", "before", "between", "through",
    "test", "tests", "testing", "tested", "page", "expect", "expected",
    "error", "errors", "timeout",
}


def _tokenize(text: str) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if len(w) >= MIN_TOKEN_LEN and w not in _STOPWORDS}


# --- Strict mode: area-wide cross-referencing only --------------------------
#
# match_failure() was designed for one-failure-at-a-time review-queue
# suggestions, where a loose floor is fine — a human reviews each
# suggestion individually. Applied across a whole area's history (every
# failed/errored run checked against every one of that area's confirmed
# issues), that same loose floor turns almost every failure into a
# "connected" test: MATCH_FLOOR only requires score > 1.5, and AREA_BONUS
# alone is 1.5 — so a single incidental shared word is enough to cross it
# once the area matches. Validated against this repo's real
# results/history/*.json and netropy-ui-findings.md, that single shared
# word is very often the area token itself spelled out as an ordinary
# word ("t10", present in nearly every T10 test's nodeid *and* in the
# finding's own body wherever it says "confirmed on T10...") — which is
# really AREA_BONUS counting itself a second time — or generic
# Playwright/page-chrome boilerplate (accessibility-tree dumps, login-
# page furniture, "Call log:" preambles) that shows up in failures
# regardless of what actually broke.
#
# Strict mode (used only by the area-detail endpoint's cross-referencing
# loop — never by the single-failure review-queue path) fixes both:
# tokens matching either category are excluded before scoring, and the
# resulting overlap must, on its own, with no help from AREA_BONUS, clear
# a much higher floor. Non-strict callers are completely unaffected —
# they never call _strict_filter and never see STRICT_OVERLAP_FLOOR.
STRICT_OVERLAP_FLOOR = 11  # strict: real overlap alone must exceed this

_AREA_WORD_RE = re.compile(r"^t\d{1,2}$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# Playwright/browser-chrome and page-furniture words that recur in nearly
# every failure message on this app regardless of topic (accessibility-
# tree dumps of the nav/login chrome, "Call log:" preambles, etc.) — real
# signal for a *specific* bug is never carried by these on their own.
_STRICT_NOISE_WORDS = {
    "img", "text", "textbox", "button", "link", "url", "apposite",
    "technologies", "traffic", "generator", "sign", "username",
    "password", "call", "log", "waiting", "navigating", "locator",
    "expected", "actual", "value", "count", "still", "empty", "never",
    "assert", "assertionerror", "powered", "reachable", "unreachable",
    "controller", "backend", "running", "online", "unit", "local",
    "www", "https", "http", "com", "org", "netropy",
}


def _strict_filter(tokens: set[str]) -> set[str]:
    return {
        t for t in tokens
        if t not in _STRICT_NOISE_WORDS
        and not _AREA_WORD_RE.match(t)
        and not _YEAR_RE.match(t)
    }


def _infer_area(body: str) -> Optional[str]:
    match = _AREA_TOKEN_RE.search(body)
    if match:
        return f"T{match.group(1)}"
    match = _AREA_FILEPATH_RE.search(body)
    return f"T{match.group(1)}" if match else None


def _split_section(text: str, header: str) -> Optional[str]:
    """Return the raw text of the "## <header>" section — everything
    after that heading line up to (not including) the next "## " heading
    — or None if `header` isn't present at all."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


# --- Status classification --------------------------------------------------
#
# The findings doc's own "Status: <free text>" line (when present) is
# deliberately loose prose written for a human reader — not a fixed
# vocabulary, and this is deliberately NOT the place to impose one on
# Logan's future writing (see the task this was built from). This is a
# lightweight keyword classifier layered on top instead, in the same
# deliberately-dumb spirit as match_failure() above: three buckets,
# keyword signals tuned against this doc's *actual* language, conservative
# by default. "Conservative" means biased toward the least-resolved
# bucket whenever signals are absent, weak, or contradictory — e.g. an
# entry that only fixed part of the picture (a test-side workaround for a
# still-open product bug — see the 15-char-name-limit finding) must never
# read as STATUS_FIXED just because the word "fixed" appears in it.
STATUS_OPEN = "open"
STATUS_INVESTIGATING = "investigating"
STATUS_FIXED = "fixed"

# Most entries carry an explicit "Status: ..." line/paragraph near the end
# of the body (not always right at the end — a couple fold an "Update:"
# sentence into the same paragraph); when present, classification looks
# at that text alone rather than the whole entry, so an incidental
# "fixed"/"pending" elsewhere in the descriptive body (e.g. inside a list
# of fix *options*) can't skew the verdict. DOTALL + non-greedy-to-end is
# fine here since `body` is already just one entry's text with no further
# "### " headings inside it.
_STATUS_LINE_RE = re.compile(r"status:\s*(.+)", re.IGNORECASE | re.DOTALL)

# Any of these near a "fixed"-leaning word means the fix is scoped,
# contested, or explicitly not-yet-real — never a clean product-side
# resolution. Overrides an otherwise-FIXED verdict back down. Named
# example: "root cause confirmed and fixed **test-side** ... Both
# product-side issues above are **still open**, pending Travis."
_FIX_CONTESTED_RE = re.compile(
    r"still open|open,? pending|remains? open|not yet fixed|test-side only"
    r"|test-side\b|unresolved",
    re.IGNORECASE,
)

_FIXED_RE = re.compile(
    r"\bfixed\b|\bresolved\b|\bno longer reproduces\b|\bconfirmed fixed\b",
    re.IGNORECASE,
)

# Deliberately loose, drawn from this doc's real recurring phrasing for
# "we've looked at this but it isn't nailed down yet": intermittency,
# single/partial reproductions, explicit "not yet confirmed" hedges, and
# open questions still awaiting someone's follow-up.
_INVESTIGATING_RE = re.compile(
    r"unresolved|intermittent|\bpending\b|not yet confirmed|not yet fully confirmed"
    r"|single observation|strong lead|unconfirmed|no confirmed root cause"
    r"|not yet root.?caused|working hypothesis|worth a (?:deliberate|direct)"
    r"|reproduced (?:twice|again|across)|deeper diagnostics|not yet.{0,20}issue"
    r"|strong.{0,10}lead",
    re.IGNORECASE,
)


def classify_status(title: str, body: str) -> str:
    """Infer STATUS_OPEN / STATUS_INVESTIGATING / STATUS_FIXED from one
    finding's title+body. Prefers an explicit "Status: ..." line/
    paragraph when the entry has one (the common case, but not universal
    — some entries, e.g. "Copy UID silently does nothing," have none at
    all); falls back to scanning the whole entry when it doesn't. Checks
    FIXED first (with the contested-fix override applied), then
    INVESTIGATING, defaulting to OPEN — the least-resolved bucket —
    whenever nothing tips it further. Never raises."""
    match = _STATUS_LINE_RE.search(body)
    status_text = match.group(1) if match else f"{title}\n{body}"

    if _FIXED_RE.search(status_text) and not _FIX_CONTESTED_RE.search(status_text):
        return STATUS_FIXED
    if _INVESTIGATING_RE.search(status_text):
        return STATUS_INVESTIGATING
    return STATUS_OPEN


def parse_confirmed_issues(findings_path: Path = DEFAULT_FINDINGS_PATH) -> list[dict]:
    """Parse the "## Confirmed product issues" section of the findings doc
    into a list of `{title, body, area, status}` dicts, one per "### "-
    level entry. `area` is inferred by scanning the body for a T-number
    token (e.g. "T10") and is None if none is found. `status` is one of
    STATUS_OPEN / STATUS_INVESTIGATING / STATUS_FIXED, inferred by
    `classify_status` — see its docstring for how. Returns [] if the file
    or the section is missing — never raises, since an edited/absent
    findings doc must never break the dashboard."""
    try:
        text = findings_path.read_text()
    except OSError:
        return []

    section = _split_section(text, CONFIRMED_SECTION_HEADER)
    if section is None:
        return []

    findings: list[dict] = []
    title: Optional[str] = None
    body_lines: list[str] = []

    def _flush() -> None:
        if title is not None:
            body = "\n".join(body_lines).strip()
            findings.append(
                {
                    "title": title,
                    "body": body,
                    "area": _infer_area(body),
                    "status": classify_status(title, body),
                }
            )

    for line in section.splitlines():
        if line.startswith("### "):
            _flush()
            title = line[len("### "):].strip()
            body_lines = []
        else:
            body_lines.append(line)
    _flush()

    return findings


def match_failure(
    nodeid: str,
    failure_message: Optional[str],
    area: Optional[str],
    findings_path: Path = DEFAULT_FINDINGS_PATH,
    strict: bool = False,
) -> list[dict]:
    """Score every confirmed finding against this failure by shared
    significant keywords between (`failure_message` + the test's own
    name, the last `::`-separated segment of `nodeid`) and each finding's
    title+body, plus a bonus when `area` matches the finding's inferred
    area. Returns the top 1-3 matches scoring above a low floor, each as
    `{"title", "score", "label": "possible match — review"}` — an empty
    list when nothing clears the floor, since noisy near-misses are worse
    than no suggestion. Never claims certainty; never auto-links.

    `strict=False` (the default) is the original single-failure
    review-queue behavior, unchanged: a loose floor appropriate when a
    human reviews each suggestion individually.

    `strict=True` is for the area-detail endpoint's cross-referencing
    loop — checking *every* failed/errored run in an area against *every*
    one of that area's confirmed issues — where the loose floor produces
    near-blanket matches (see `_strict_filter`'s docstring above). It
    excludes area-token and page-boilerplate noise from both sides before
    scoring, and requires the remaining keyword overlap to clear
    `STRICT_OVERLAP_FLOOR` *on its own*, independent of AREA_BONUS."""
    findings = parse_confirmed_issues(findings_path)
    if not findings:
        return []

    test_name = nodeid.rsplit("::", 1)[-1] if nodeid else ""
    query_tokens = _tokenize(f"{failure_message or ''} {test_name}")
    if strict:
        query_tokens = _strict_filter(query_tokens)
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for finding in findings:
        finding_tokens = _tokenize(f"{finding['title']} {finding['body']}")
        if strict:
            finding_tokens = _strict_filter(finding_tokens)
        overlap = query_tokens & finding_tokens
        score = float(len(overlap))
        if area and finding.get("area") and finding["area"] == area:
            score += AREA_BONUS
        if strict:
            if len(overlap) <= STRICT_OVERLAP_FLOOR:
                continue
        elif score <= MATCH_FLOOR:
            continue
        scored.append((score, finding))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"title": finding["title"], "score": score, "label": MATCH_LABEL}
        for score, finding in scored[:MAX_MATCHES]
    ]
