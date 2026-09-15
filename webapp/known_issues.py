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


def _infer_area(body: str) -> Optional[str]:
    match = _AREA_TOKEN_RE.search(body)
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


def parse_confirmed_issues(findings_path: Path = DEFAULT_FINDINGS_PATH) -> list[dict]:
    """Parse the "## Confirmed product issues" section of the findings doc
    into a list of `{title, body, area}` dicts, one per "### "-level
    entry. `area` is inferred by scanning the body for a T-number token
    (e.g. "T10") and is None if none is found. Returns [] if the file or
    the section is missing — never raises, since an edited/absent
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
            findings.append({"title": title, "body": body, "area": _infer_area(body)})

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
) -> list[dict]:
    """Score every confirmed finding against this failure by shared
    significant keywords between (`failure_message` + the test's own
    name, the last `::`-separated segment of `nodeid`) and each finding's
    title+body, plus a bonus when `area` matches the finding's inferred
    area. Returns the top 1-3 matches scoring above a low floor, each as
    `{"title", "score", "label": "possible match — review"}` — an empty
    list when nothing clears the floor, since noisy near-misses are worse
    than no suggestion. Never claims certainty; never auto-links."""
    findings = parse_confirmed_issues(findings_path)
    if not findings:
        return []

    test_name = nodeid.rsplit("::", 1)[-1] if nodeid else ""
    query_tokens = _tokenize(f"{failure_message or ''} {test_name}")
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for finding in findings:
        finding_tokens = _tokenize(f"{finding['title']} {finding['body']}")
        overlap = query_tokens & finding_tokens
        score = float(len(overlap))
        if area and finding.get("area") and finding["area"] == area:
            score += AREA_BONUS
        if score > MATCH_FLOOR:
            scored.append((score, finding))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"title": finding["title"], "score": score, "label": MATCH_LABEL}
        for score, finding in scored[:MAX_MATCHES]
    ]
