# Local Test Runner Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, browser-based dashboard (`python -m webapp.app`) that lets a non-technical user browse this repo's Playwright tests, run one with a click, watch it go live, and check persisted results — no terminal, no Playwright/pytest knowledge required.

**Architecture:** FastAPI backend (catalog discovery via static AST parsing, one-batch-at-a-time subprocess orchestration, Server-Sent Events for live status) + vanilla HTML/CSS/JS frontend, no build step. Reuses the existing `results/history/*.json` format and `conftest.py` hook unchanged — a batch-triggered run is just a normal pytest invocation with one extra env var.

**Tech Stack:** Python 3.9 (matches the repo), FastAPI + Uvicorn (new deps), vanilla JS/CSS (no Node, no npm). Inter (Google Fonts) for typography.

**Spec:** `docs/superpowers/specs/2026-09-10-test-runner-webapp-design.md`

## Global Constraints

- No Node/npm/build step anywhere in `webapp/` — plain `<script>`/`<link>` tags, no bundler.
- `webapp/`'s own backend unit tests must never trigger the repo-root `conftest.py`'s `pytest_sessionfinish` hook — always run them with `--confcutdir=webapp` (see Task 3+).
- Exactly one test batch runs at a time, globally, enforced server-side (not just UI-suggested) — CLAUDE.md's "never run stateful tests in parallel" rule, satisfied by construction.
- A `stateful` test's run prompt must show the plain-language notice *"This generates real network traffic on the lab hardware."* before it starts.
- All `repeat_count` iterations always run to completion, even after an earlier one fails — matches the existing "Stability run" convention in CLAUDE.md.
- Existing CLI-driven `pytest -m hardware_free` / `-m stateful` workflow and the existing `results/index.html` static dashboard must keep working unchanged after this is built.
- Colors/type/component styling come from `webapp/DESIGN.md` (Task 1) — no ad hoc colors/fonts introduced later in frontend tasks.
- Launch command is `python -m webapp.app` (run from repo root) — never `python webapp/app.py` directly, which breaks the `from webapp.catalog import ...` absolute import (see Task 2).

---

### Task 1: Design tokens — `webapp/DESIGN.md`

**Files:**
- Create: `webapp/DESIGN.md`

**Interfaces:**
- Produces: the color/type/component tokens every later frontend task (9-12) must use verbatim.

- [ ] **Step 1: Write the design doc**

Create `webapp/DESIGN.md`:

```markdown
# Design System — Netropy Test Dashboard

Tokens extracted from two real Netropy Traffic Generator screenshots
(main dashboard, Create Testbed modal) and the Apposite Technologies
logo, provided 2026-09-10. This is a **theme match, not a screen clone**
— colors, type, and component styling come from here; this app's own
layout (tabs, test list, run flow, results table) is shaped around what
it actually needs, not copied from Netropy's specific screens.

## Color

| Token | Value | Use |
|---|---|---|
| `--bg` | `#EEF2F8` | Page background |
| `--surface` | `#FFFFFF` | Cards, modals, table rows |
| `--surface-2` | `#F5F7FB` | Subtle secondary surface (table header, hover, disabled panel) |
| `--border` | `#DCE3EE` | Card/table/input borders |
| `--ink` | `#16294A` | Primary text, headings, big numbers |
| `--ink-dim` | `#6B7686` | Secondary text, uppercase labels |
| `--accent` | `#1D4E8F` | Primary buttons, links, selected state |
| `--accent-hover` | `#16406F` | Primary button hover |
| `--ok` | `#1F8A4C` | "Available"/"Up"/passed |
| `--ok-bg` | `#E3F5E9` | Success pill background |
| `--warn` | `#8A6D1F` | "Reserved"-style pending/warning states |
| `--warn-bg` | `#FDF3D8` | Warning pill background |
| `--bad` | `#C23B3B` | "Down"/failed |
| `--bad-bg` | `#FBEAEA` | Failure pill/badge background |
| `--muted` | `#9AA3B0` | Disabled text/buttons |

Dark mode isn't part of this pass — Netropy's own UI has none, and this
is a short-session local utility, not something left open for hours.
Revisit only if asked for.

## Typography

- **Font:** Inter (Google Fonts), falling back to
  `-apple-system, "Segoe UI", Roboto, sans-serif`.
- **Scale:** 12px (uppercase labels, tracked +0.04em) / 14px (body,
  table cells) / 16px (section headings) / 28px (big stat numbers).
- Uppercase labels: `letter-spacing: 0.04em`, `color: var(--ink-dim)`,
  `font-weight: 600`.

## Buttons

- **Primary** ("Run", "Reserve"-style): `background: var(--accent)`,
  white text, `border-radius: 6px`, `padding: 6px 16px`,
  `font-weight: 600`; hover darkens to `--accent-hover`.
- **Disabled**: `background: transparent`, `color: var(--muted)`, same
  padding/radius, `cursor: not-allowed`.
- **Outline** (secondary actions, e.g. "Run all"): `background: transparent`,
  `border: 1px solid var(--border)`, `color: var(--ink)`.

## Status pills

Fully rounded (`border-radius: 999px`), `padding: 2px 10px`,
`font-size: 12px`, `font-weight: 600`:
- Positive (`passed`, "Safe"): `background: var(--ok-bg)`, `color: var(--ok)`.
- Warning/pending (`queued`, `running`, "Generates traffic"): `background: var(--warn-bg)`, `color: var(--warn)`.
- Negative (`failed`, `error`): `background: var(--bad-bg)`, `color: var(--bad)`.

## Cards

`background: var(--surface)`, `border: 1px solid var(--border)`,
`border-radius: 10px`, no heavy shadow — Netropy's own cards are flat
and bordered, not shadowed.

## Tables

Header row: `background: var(--surface-2)`, uppercase label style,
`border-bottom: 1px solid var(--border)`. Body rows:
`border-bottom: 1px solid var(--border)`, no zebra striping.

## Tiles (selectable/disabled cards)

`border: 1px solid var(--border)`, `border-radius: 8px`, `padding: 12px`;
selected: `border-color: var(--accent)`, `box-shadow: 0 0 0 1px var(--accent)`;
disabled ("coming soon"): `opacity: 0.5`, `cursor: not-allowed`.

## Modals

`background: var(--surface)`, `border-radius: 12px`,
`box-shadow: 0 10px 40px rgba(15,30,60,0.18)`, centered on a
semi-transparent dark scrim (`rgba(10,20,40,0.35)`).

## Tooltips

Dark: `background: #16294A`, white text, `border-radius: 6px`,
`padding: 4px 10px`, `font-size: 12px`.

## Logo

`webapp/static/apposite-logo.png` — header, left-aligned, ~28px tall,
next to the app name in `--ink`.
```

- [ ] **Step 2: Copy the logo asset**

```bash
mkdir -p webapp/static
cp "/Users/loganzeto/Downloads/ap logo.png" webapp/static/apposite-logo.png
```

- [ ] **Step 3: Commit**

```bash
git add webapp/DESIGN.md webapp/static/apposite-logo.png
git commit -m "docs: add webapp design tokens + logo asset"
```

---

### Task 2: Project scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `webapp/__init__.py` (empty)
- Modify: `Makefile`

**Interfaces:**
- Produces: `webapp` as an importable package from the repo root; `make run-dashboard` as the launch command.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:
```
fastapi>=0.115
uvicorn>=0.30
httpx>=0.27
```
(`httpx` is needed for FastAPI's `TestClient` used in later tasks' tests, not for the app itself.)

- [ ] **Step 2: Install and verify**

```bash
source .venv/bin/activate && pip install -r requirements.txt
python -c "import fastapi, uvicorn, httpx; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Create the package**

```bash
touch webapp/__init__.py
```

- [ ] **Step 4: Add the Makefile target**

Add to `Makefile` (alongside the existing `report` target):
```makefile
.PHONY: run-dashboard

# Launch the local test-runner web app. Must be -m (module), not a direct
# script path — webapp/app.py does `from webapp.catalog import ...`,
# which only resolves if the repo root (not webapp/) is on sys.path, and
# only `python -m webapp.app` (run from the repo root) does that.
run-dashboard:
	python -m webapp.app
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt webapp/__init__.py Makefile
git commit -m "chore: scaffold webapp package, add fastapi/uvicorn/httpx deps"
```

---

### Task 3: `webapp/catalog.py` — static test discovery

**Files:**
- Create: `webapp/catalog.py`
- Test: `webapp/tests/test_catalog.py`
- Create: `webapp/tests/__init__.py` (empty)

**Interfaces:**
- Produces:
  - `TestEntry(nodeid: str, name: str, markers: list[str])` with property `.safety_marker -> Optional[str]`
  - `TestFile(path: str, short_description: str, full_description: str, tests: list[TestEntry])`
  - `TestGroup(id: str, label: str, files: list[TestFile])` with property `.run_all_nodeids -> list[str]`
  - `discover_groups(tests_root: Path = TESTS_ROOT, repo_root: Path = REPO_ROOT) -> list[TestGroup]`

- [ ] **Step 1: Write the failing tests**

Create `webapp/tests/__init__.py` (empty file).

Create `webapp/tests/test_catalog.py`:

```python
"""Unit tests for webapp/catalog.py — pure AST parsing, no pytest suite
dependency, no browser. Run with:
    pytest --confcutdir=webapp webapp/tests/test_catalog.py -v
(--confcutdir keeps this from picking up the repo-root conftest.py, which
is for the real Playwright suite and would otherwise try to write a
results/history entry for these unit tests too.)
"""
from pathlib import Path

from webapp.catalog import discover_groups, _group_label, _is_combined_suite_file


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_group_label_single_number():
    assert _group_label("t1_auth") == "T1 — Auth"


def test_group_label_multi_number():
    assert _group_label("t10_t12_lifecycle") == "T10/T12 — Lifecycle"


def test_group_label_multi_word():
    assert _group_label("t3_port_management") == "T3 — Port Management"


def test_combined_suite_exact_match_excluded():
    assert _is_combined_suite_file("t1_auth_all", "t1_auth") is True


def test_combined_suite_false_positive_not_excluded():
    # test_t7_frame_size_apply_to_all.py — a real, distinct test, not a
    # combined-suite file, despite ending in "_all".
    assert _is_combined_suite_file("t7_frame_size_apply_to_all", "t7_streams") is False


def test_discover_groups_end_to_end(tmp_path):
    tests_root = tmp_path / "tests"

    _write(
        tests_root / "t1_auth" / "test_t1_valid_login.py",
        '''"""T1 — valid login lands on dashboard.

More detail here.
"""
import pytest


@pytest.mark.hardware_free
@pytest.mark.smoke
def test_t1_valid_login(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t1_auth" / "test_t1_auth_all.py",
        '''"""T1 — combined suite, should not appear."""
import pytest


@pytest.mark.hardware_free
def test_t1_valid_login(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t7_streams" / "test_t7_frame_size_apply_to_all.py",
        '''"""T7 — frame size apply-to-all sticks per row."""
import pytest


@pytest.mark.hardware_free
def test_t7_frame_size_apply_to_all_then_per_row_edit_sticks(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t10_t12_lifecycle" / "test_t10_t12_lifecycle_arp.py",
        '''"""T10/T12 — ARP lifecycle."""
import pytest


@pytest.mark.stateful
def test_t10_t12_lifecycle_arp(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t9_network_profiles" / "test_t9_quarantined_thing.py",
        '''"""T9 — a known-flaky test, should not appear."""
import pytest


@pytest.mark.hardware_free
@pytest.mark.quarantine
def test_t9_quarantined_thing(dashboard):
    pass
''',
    )

    groups = discover_groups(tests_root, repo_root=tmp_path)
    labels = {g.label for g in groups}
    assert labels == {"T1 — Auth", "T7 — Streams", "T10/T12 — Lifecycle"}

    t1 = next(g for g in groups if g.id == "t1_auth")
    assert [f.path for f in t1.files] == ["tests/t1_auth/test_t1_valid_login.py"]
    assert t1.files[0].short_description == "T1 — valid login lands on dashboard."
    entry = t1.files[0].tests[0]
    assert entry.nodeid == "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"
    assert entry.markers == ["hardware_free", "smoke"]
    assert entry.safety_marker == "hardware_free"

    # t9's only test is quarantined -> zero visible tests -> group excluded
    assert "t9_network_profiles" not in {g.id for g in groups}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate
pytest --confcutdir=webapp webapp/tests/test_catalog.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.catalog'`

- [ ] **Step 3: Write the implementation**

Create `webapp/catalog.py`:

```python
"""Static, AST-based discovery of the Playwright test suite for the web
dashboard. Never imports or invokes pytest — this only reads source
files, so opening the dashboard can't reserve a port or touch the box by
itself.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = REPO_ROOT / "tests"

SAFETY_MARKERS = {"hardware_free", "stateful"}
_AREA_TOKEN_RE = re.compile(r"^t\d+$")


@dataclass
class TestEntry:
    nodeid: str
    name: str
    markers: list[str]

    @property
    def safety_marker(self) -> Optional[str]:
        for m in self.markers:
            if m in SAFETY_MARKERS:
                return m
        return None


@dataclass
class TestFile:
    path: str
    short_description: str
    full_description: str
    tests: list[TestEntry] = field(default_factory=list)


@dataclass
class TestGroup:
    id: str
    label: str
    files: list[TestFile] = field(default_factory=list)

    @property
    def run_all_nodeids(self) -> list[str]:
        return [t.nodeid for f in self.files for t in f.tests]


def _group_label(dirname: str) -> str:
    """'t10_t12_lifecycle' -> 'T10/T12 — Lifecycle'; 't1_auth' -> 'T1 — Auth'."""
    tokens = dirname.split("_")
    numbers = []
    i = 0
    while i < len(tokens) and _AREA_TOKEN_RE.match(tokens[i]):
        numbers.append(tokens[i].upper())
        i += 1
    rest = " ".join(t.capitalize() for t in tokens[i:])
    prefix = "/".join(numbers) if numbers else dirname.upper()
    return f"{prefix} — {rest}" if rest else prefix


def _is_combined_suite_file(file_stem: str, dirname: str) -> bool:
    """True only for an exact '<dirname>_all' stem — a loose '_all.py'
    suffix check would also match genuinely distinct tests like
    test_t7_frame_size_apply_to_all.py (its own name, not the
    combined-suite convention)."""
    return file_stem == f"{dirname}_all"


def _decorator_marker_name(node: ast.expr) -> Optional[str]:
    """@pytest.mark.hardware_free -> 'hardware_free' (bare attribute);
    @pytest.mark.xfail(...) -> 'xfail' (a call wrapping the same
    attribute chain)."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute):
        if target.value.attr == "mark":
            return target.attr
    return None


def _parse_file(path: Path, repo_root: Path) -> Optional[TestFile]:
    tree = ast.parse(path.read_text(), filename=str(path))
    docstring = ast.get_docstring(tree) or ""
    if not docstring:
        return None
    short = docstring.strip().splitlines()[0].strip()

    tests: list[TestEntry] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        markers = [
            m for m in (_decorator_marker_name(dec) for dec in node.decorator_list) if m
        ]
        if "quarantine" in markers:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        tests.append(
            TestEntry(nodeid=f"{rel_path}::{node.name}", name=node.name, markers=markers)
        )

    if not tests:
        return None

    return TestFile(
        path=path.relative_to(repo_root).as_posix(),
        short_description=short,
        full_description=docstring.strip(),
        tests=tests,
    )


def discover_groups(
    tests_root: Path = TESTS_ROOT, repo_root: Path = REPO_ROOT
) -> list[TestGroup]:
    groups: list[TestGroup] = []
    for dir_path in sorted(p for p in tests_root.iterdir() if p.is_dir()):
        dirname = dir_path.name
        if dirname.startswith("__"):
            continue
        files: list[TestFile] = []
        for file_path in sorted(dir_path.glob("test_*.py")):
            if _is_combined_suite_file(file_path.stem, dirname):
                continue
            parsed = _parse_file(file_path, repo_root)
            if parsed:
                files.append(parsed)
        if files:
            groups.append(TestGroup(id=dirname, label=_group_label(dirname), files=files))
    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest --confcutdir=webapp webapp/tests/test_catalog.py -v
```
Expected: 6 passed

- [ ] **Step 5: Sanity-check against the real repo**

```bash
python -c "
from webapp.catalog import discover_groups
for g in discover_groups():
    print(g.label, '-', len(g.files), 'files')
"
```
Expected: one line per real `tests/` subdirectory with files, labels matching the spec's examples (T1 — Auth, T10/T12 — Lifecycle, etc.), no `_all.py` combined files counted, no quarantined-only files.

- [ ] **Step 6: Commit**

```bash
git add webapp/catalog.py webapp/tests/
git commit -m "feat(webapp): AST-based test catalog discovery"
```

---

### Task 4: `scripts/collect_run.py` extensions — `batch_id` + `trace`

**Files:**
- Modify: `scripts/collect_run.py`
- Test: `webapp/tests/test_collect_run_extensions.py`

**Interfaces:**
- Consumes: `scripts.artifact_paths.slugify` (existing).
- Produces: `build_summary(..., batch_id: Optional[str] = None)` — adds `"batch_id"` key to the returned dict only when truthy; `collect(..., batch_id: Optional[str] = None)` — defaults to `os.environ.get("NETROPY_WEBAPP_BATCH_ID")` when not passed explicitly; `_trace_for(nodeid: str, artifacts_dir: Path) -> Optional[str]` (new helper, same shape as the existing `_screenshot_for`); each test dict gains a `"trace"` key.

- [ ] **Step 1: Write the failing tests**

Create `webapp/tests/test_collect_run_extensions.py`:

```python
"""Unit tests for the webapp-related additions to scripts/collect_run.py
(batch_id tagging, trace-file lookup). Run with:
    pytest --confcutdir=webapp webapp/tests/test_collect_run_extensions.py -v
"""
import os
from pathlib import Path

from scripts.collect_run import _trace_for, build_summary


def _write_junit(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0"?>'
        '<testsuites><testsuite time="1.5">'
        '<testcase classname="tests.t1_auth.test_t1_valid_login" '
        'name="test_t1_valid_login[chromium]" time="1.5" '
        'file="tests/t1_auth/test_t1_valid_login.py" /></testsuite></testsuites>'
    )


def test_build_summary_omits_batch_id_when_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("NETROPY_WEBAPP_BATCH_ID", raising=False)
    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    summary = build_summary(junit, artifacts_dir=tmp_path / "artifacts")
    assert "batch_id" not in summary


def test_build_summary_includes_batch_id_when_passed(tmp_path):
    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    summary = build_summary(junit, artifacts_dir=tmp_path / "artifacts", batch_id="abc-123")
    assert summary["batch_id"] == "abc-123"


def test_trace_for_finds_existing_trace(tmp_path):
    from scripts.artifact_paths import slugify

    nodeid = "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"
    artifacts_dir = tmp_path / "artifacts"
    trace_dir = artifacts_dir / slugify(nodeid)
    trace_dir.mkdir(parents=True)
    (trace_dir / "trace.zip").write_bytes(b"fake")

    result = _trace_for(nodeid, artifacts_dir)
    assert result == f"artifacts/{slugify(nodeid)}/trace.zip"


def test_trace_for_returns_none_when_absent(tmp_path):
    assert _trace_for("tests/x.py::test_x", tmp_path / "artifacts") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest --confcutdir=webapp webapp/tests/test_collect_run_extensions.py -v
```
Expected: FAIL — `_trace_for` doesn't exist yet, and `build_summary`/`collect` don't accept `batch_id`.

- [ ] **Step 3: Modify `scripts/collect_run.py`**

Add this function near `_screenshot_for` (same file):

```python
def _trace_for(nodeid: str, artifacts_dir: Path) -> Optional[str]:
    """Same convention as _screenshot_for, but for the trace.zip a
    webapp-triggered run's page fixture saves on failure (see
    conftest.py). Always safe to call for every run — returns None when
    no trace exists, which is the normal case for plain CLI-triggered
    runs (tracing is gated off for those)."""
    try:
        from scripts.artifact_paths import slugify
    except Exception:
        return None
    trace_path = artifacts_dir / slugify(nodeid) / "trace.zip"
    if trace_path.exists():
        try:
            return str(trace_path.relative_to(artifacts_dir.parent))
        except ValueError:
            return str(trace_path)
    return None
```

In `_parse_testcase`, add the trace field to the returned dict (find the existing `return {` block ending in `"screenshot": _screenshot_for(nodeid, artifacts_dir),` and add a line after it):

```python
        "screenshot": _screenshot_for(nodeid, artifacts_dir),
        "trace": _trace_for(nodeid, artifacts_dir),
    }
```

In `build_summary`, add the `batch_id` parameter and conditionally include it:

```python
def build_summary(
    junit_path: Path = DEFAULT_JUNIT,
    markers: str = "",
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    run_time: Optional[datetime] = None,
    batch_id: Optional[str] = None,
) -> Optional[dict]:
```

(keep the existing body up through building `tests`, then change the final return to:)

```python
    summary = {
        "run_id": run_id,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "--short", "HEAD") or "unknown",
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "markers": markers or "",
        "duration": round(total_duration, 3),
        "tests": tests,
    }
    if batch_id:
        summary["batch_id"] = batch_id
    return summary
```

In `collect()`, add the parameter and default it from the env var, then pass through:

```python
def collect(
    junit_path: Path = DEFAULT_JUNIT,
    history_dir: Path = DEFAULT_HISTORY_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    markers: str = "",
    batch_id: Optional[str] = None,
) -> Optional[Path]:
    """High-level entry point: parse + write. Returns the written path, or
    None if there was nothing collectible (never raises)."""
    if batch_id is None:
        batch_id = os.environ.get("NETROPY_WEBAPP_BATCH_ID")
    summary = build_summary(
        junit_path, markers=markers, artifacts_dir=artifacts_dir, batch_id=batch_id
    )
    if summary is None:
        return None
    return write_summary(summary, history_dir)
```

(`os` is already imported at the top of `scripts/collect_run.py`.) No changes needed to `conftest.py`'s call site (`collect_run.collect(markers=markers)`) — it picks up the env var automatically.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest --confcutdir=webapp webapp/tests/test_collect_run_extensions.py -v
```
Expected: 4 passed

- [ ] **Step 5: Re-run the existing collect_run/build_report tests manually to confirm no regression**

```bash
python -m pytest tests/t2_dashboard/ -m hardware_free -q
cat "$(ls -t results/history/*.json | head -1)" | python3 -c "import json,sys; d=json.load(sys.stdin); print('batch_id' in d)"
```
Expected: the suite still passes, and prints `False` (a normal CLI run has no batch_id — confirms the additive change doesn't affect existing behavior).

- [ ] **Step 6: Commit**

```bash
git add scripts/collect_run.py webapp/tests/test_collect_run_extensions.py
git commit -m "feat: add batch_id + trace fields to collect_run.py, gated/optional"
```

---

### Task 5: Trace capture in `conftest.py`, gated to webapp-triggered runs

**Files:**
- Modify: `conftest.py`

**Interfaces:**
- Consumes: `os.environ["NETROPY_WEBAPP_BATCH_ID"]` (set by `webapp/runner.py` in Task 7).
- Produces: `<results/artifacts>/<slugify(nodeid)>/trace.zip` on failure, for any test run with that env var set.

This one can't be meaningfully unit-tested without a real browser/box —
verified manually against the real box at the end of this task, same as
the existing screenshot capture was.

- [ ] **Step 1: Modify the `page` fixture**

In `conftest.py`, in the `page` fixture, right after `context.add_init_script(init_script)` and before `pg = context.new_page()`, add:

```python
    # Tracing is only captured for runs the web dashboard triggers (see
    # webapp/runner.py, which sets NETROPY_WEBAPP_BATCH_ID) — the existing
    # CLI-driven suite's disk usage and behavior stay exactly as they are.
    capture_trace = bool(os.environ.get("NETROPY_WEBAPP_BATCH_ID"))
    if capture_trace:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
```

Then, in the teardown section (after `yield pg`), right after the existing screenshot-capture `if screenshot_option == ...:` block and before `context.close()`, add:

```python
    # retain-on-failure: only keep the trace file for a failed run; still
    # call stop() either way to end the tracing session cleanly.
    if capture_trace:
        try:
            from scripts.artifact_paths import slugify

            output_dir = pathlib.Path(pytestconfig.getoption("--output"))
            test_dir = output_dir / slugify(request.node.nodeid)
            if failed:
                test_dir.mkdir(parents=True, exist_ok=True)
                context.tracing.stop(path=str(test_dir / "trace.zip"))
            else:
                context.tracing.stop()
        except Exception:
            pass
```

(`os` and `pathlib` are already imported at the top of `conftest.py`.)

- [ ] **Step 2: Verify with a real deliberate failure**

```bash
source .venv/bin/activate
NETROPY_WEBAPP_BATCH_ID=test-batch-1 python -m pytest tests/t2_dashboard/ -m hardware_free -q
find results/artifacts -name "trace.zip"
```
Expected: no trace.zip yet (nothing failed in that run) — this just confirms tracing doesn't break a passing run. Then force a real failure the same way Task-writing did earlier this project (temporarily point a `get_by_text` at nonexistent text in a throwaway `test_zzscratch_*.py` file under `tests/t2_dashboard/`, run it the same way with the env var set, confirm a `trace.zip` appears next to the `test-failed-1.png`, then delete the throwaway file and its stray `results/history` entry).

- [ ] **Step 3: Confirm no trace without the env var**

```bash
python -m pytest tests/t2_dashboard/ -m hardware_free -q
find results/artifacts -name "trace.zip"
```
Expected: still only the one trace.zip from Step 2 (none new) — confirms plain CLI runs are unaffected.

- [ ] **Step 4: Commit**

```bash
git add conftest.py
git commit -m "feat: capture Playwright trace on failure, gated to webapp-triggered runs"
```

---

### Task 6: `webapp/persistence.py` — Results page data

**Files:**
- Create: `webapp/persistence.py`
- Test: `webapp/tests/test_persistence.py`

**Interfaces:**
- Produces:
  - `IterationResult(run_id, timestamp, outcome, duration, failure_message, screenshot, trace)`
  - `BatchResult(batch_id, nodeid, iterations: list[IterationResult])` with properties `.pass_count`, `.total_duration`, `.started_at`
  - `list_batches(history_dir: Path = HISTORY_DIR) -> list[BatchResult]` — only entries carrying a `batch_id`, newest batch first, iterations sorted oldest-first within a batch.

- [ ] **Step 1: Write the failing tests**

Create `webapp/tests/test_persistence.py`:

```python
"""Run with: pytest --confcutdir=webapp webapp/tests/test_persistence.py -v"""
import json
from pathlib import Path

from webapp.persistence import list_batches


def _write_history(history_dir: Path, run_id: str, batch_id, nodeid: str, outcome: str, ts: str):
    history_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "timestamp": ts,
        "git_sha": "abc123",
        "git_branch": "main",
        "markers": "hardware_free",
        "duration": 1.5,
        "tests": [
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "duration": 1.5,
                "failure_message": None if outcome == "pass" else "boom",
                "screenshot": None,
                "trace": None,
            }
        ],
    }
    if batch_id:
        data["batch_id"] = batch_id
    (history_dir / f"{run_id}.json").write_text(json.dumps(data))


def test_ignores_runs_without_batch_id(tmp_path):
    _write_history(tmp_path, "run1", None, "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    assert list_batches(tmp_path) == []


def test_groups_iterations_by_batch_id(tmp_path):
    _write_history(tmp_path, "run1", "batch-a", "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    _write_history(tmp_path, "run2", "batch-a", "tests/x.py::test_x", "fail", "2026-01-01T00:01:00Z")
    _write_history(tmp_path, "run3", "batch-b", "tests/y.py::test_y", "pass", "2026-01-01T00:02:00Z")

    batches = list_batches(tmp_path)
    assert len(batches) == 2
    # newest batch first
    assert batches[0].batch_id == "batch-b"
    assert batches[1].batch_id == "batch-a"

    batch_a = batches[1]
    assert batch_a.nodeid == "tests/x.py::test_x"
    assert len(batch_a.iterations) == 2
    assert batch_a.pass_count == 1
    assert batch_a.total_duration == 3.0
    assert batch_a.started_at == "2026-01-01T00:00:00Z"
    # iterations sorted oldest-first within the batch
    assert [i.outcome for i in batch_a.iterations] == ["pass", "fail"]


def test_skips_malformed_history_file(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "broken.json").write_text("{not valid json")
    _write_history(tmp_path, "run1", "batch-a", "tests/x.py::test_x", "pass", "2026-01-01T00:00:00Z")
    batches = list_batches(tmp_path)
    assert len(batches) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest --confcutdir=webapp webapp/tests/test_persistence.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.persistence'`

- [ ] **Step 3: Write the implementation**

Create `webapp/persistence.py`:

```python
"""Reads results/history/*.json for the web dashboard's Results page.
Read-only — this never writes; results/history/ is written by the
existing conftest.py pytest_sessionfinish hook (scripts/collect_run.py),
unchanged, for every pytest session including the ones this app
triggers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = REPO_ROOT / "results" / "history"


@dataclass
class IterationResult:
    run_id: str
    timestamp: str
    outcome: str
    duration: float
    failure_message: Optional[str]
    screenshot: Optional[str]
    trace: Optional[str]


@dataclass
class BatchResult:
    batch_id: str
    nodeid: str
    iterations: list[IterationResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for i in self.iterations if i.outcome == "pass")

    @property
    def total_duration(self) -> float:
        return sum(i.duration for i in self.iterations)

    @property
    def started_at(self) -> str:
        return min((i.timestamp for i in self.iterations), default="")


def _load_history(history_dir: Path) -> list[dict]:
    runs = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            runs.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue  # same defensive skip as scripts/build_report.py
    return runs


def list_batches(history_dir: Path = HISTORY_DIR) -> list[BatchResult]:
    """Only web-app-triggered runs (those carrying a batch_id) — plain
    CLI runs have no batch_id and don't belong on this page."""
    batches: dict[str, BatchResult] = {}
    for run in _load_history(history_dir):
        batch_id = run.get("batch_id")
        if not batch_id:
            continue
        for test in run.get("tests", []):
            batch = batches.setdefault(
                batch_id, BatchResult(batch_id=batch_id, nodeid=test["nodeid"])
            )
            batch.iterations.append(
                IterationResult(
                    run_id=run["run_id"],
                    timestamp=run.get("timestamp", ""),
                    outcome=test["outcome"],
                    duration=test.get("duration", 0.0),
                    failure_message=test.get("failure_message"),
                    screenshot=test.get("screenshot"),
                    trace=test.get("trace"),
                )
            )
    result = list(batches.values())
    for batch in result:
        batch.iterations.sort(key=lambda i: i.timestamp)
    result.sort(key=lambda b: b.started_at, reverse=True)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest --confcutdir=webapp webapp/tests/test_persistence.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add webapp/persistence.py webapp/tests/test_persistence.py
git commit -m "feat(webapp): results/history reader grouped by batch_id"
```

---

### Task 7: `webapp/runner.py` — batch orchestration + live status

**Files:**
- Create: `webapp/runner.py`
- Test: `webapp/tests/test_runner.py`

**Interfaces:**
- Consumes: nothing from earlier tasks directly (takes `history_dir`/`subprocess_run` as injectable params for testability).
- Produces:
  - `IterationEvent(batch_id, iteration, total, status, detail=None)` — `status` in `{"running","passed","failed","error","skipped"}`
  - `BatchCompleteEvent(batch_id, passed, total)`
  - `AlreadyRunningError(Exception)`
  - `TestRunner(repo_root=REPO_ROOT, history_dir=None, subprocess_run=subprocess.run)` with:
    - `.start(nodeid: str, marker: str, repeat_count: int) -> str` (returns batch_id, raises `AlreadyRunningError` if busy)
    - `.events(batch_id: str)` — blocking generator yielding `IterationEvent`s then one final `BatchCompleteEvent`

- [ ] **Step 1: Write the failing tests**

Create `webapp/tests/test_runner.py`:

```python
"""Run with: pytest --confcutdir=webapp webapp/tests/test_runner.py -v
The real pytest subprocess call is replaced with a fake so this suite
runs in milliseconds with no browser, no box, and no real test
execution.
"""
import json
import time

import pytest

from webapp.runner import AlreadyRunningError, TestRunner


def _fake_subprocess_run_factory(history_dir, outcome="pass"):
    def _fake_run(cmd, cwd, env, capture_output, text, timeout):
        batch_id = env["NETROPY_WEBAPP_BATCH_ID"]
        nodeid = cmd[2]
        history_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"{time.time_ns()}"
        (history_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "git_sha": "abc123",
                    "git_branch": "main",
                    "markers": "hardware_free",
                    "duration": 1.23,
                    "batch_id": batch_id,
                    "tests": [
                        {
                            "nodeid": nodeid,
                            "outcome": outcome,
                            "duration": 1.23,
                            "failure_message": None if outcome == "pass" else "boom",
                            "screenshot": None,
                            "trace": None,
                        }
                    ],
                }
            )
        )

        class _Result:
            returncode = 0 if outcome == "pass" else 1

        return _Result()

    return _fake_run


def test_single_passing_run(tmp_path):
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "pass"),
    )
    batch_id = runner.start(
        "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login", "hardware_free", 1
    )
    events = list(runner.events(batch_id))
    assert [type(e).__name__ for e in events] == [
        "IterationEvent",
        "IterationEvent",
        "BatchCompleteEvent",
    ]
    assert events[0].status == "running"
    assert events[1].status == "passed"
    assert events[2].passed == 1
    assert events[2].total == 1


def test_failing_run_reports_failure_message(tmp_path):
    history_dir = tmp_path / "history"
    runner = TestRunner(
        repo_root=tmp_path,
        history_dir=history_dir,
        subprocess_run=_fake_subprocess_run_factory(history_dir, "fail"),
    )
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 1)
    events = list(runner.events(batch_id))
    assert events[1].status == "failed"
    assert events[1].detail == "boom"


def test_second_run_rejected_while_one_is_active(tmp_path):
    history_dir = tmp_path / "history"

    def _slow_fake_run(cmd, cwd, env, capture_output, text, timeout):
        time.sleep(0.2)
        return _fake_subprocess_run_factory(history_dir, "pass")(
            cmd, cwd, env, capture_output, text, timeout
        )

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_slow_fake_run)
    runner.start("tests/x.py::test_x", "hardware_free", 1)
    with pytest.raises(AlreadyRunningError):
        runner.start("tests/y.py::test_y", "hardware_free", 1)


def test_repeat_count_runs_all_iterations_even_after_failure(tmp_path):
    history_dir = tmp_path / "history"
    calls = {"n": 0}
    real_fake = _fake_subprocess_run_factory(history_dir, "fail")

    def _counting_fake(*args, **kwargs):
        calls["n"] += 1
        return real_fake(*args, **kwargs)

    runner = TestRunner(repo_root=tmp_path, history_dir=history_dir, subprocess_run=_counting_fake)
    batch_id = runner.start("tests/x.py::test_x", "hardware_free", 3)
    list(runner.events(batch_id))
    assert calls["n"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest --confcutdir=webapp webapp/tests/test_runner.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.runner'`

- [ ] **Step 3: Write the implementation**

Create `webapp/runner.py`:

```python
"""Orchestrates running one test N times via real pytest subprocesses,
tracking live per-iteration status for the SSE endpoint in app.py.
Exactly one batch runs at a time, globally — enforced here, not just
suggested in the UI, since two people could otherwise fight over the
same lab hardware from two browser tabs.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

_OUTCOME_TO_STATUS = {
    "pass": "passed",
    "fail": "failed",
    "error": "error",
    "skip": "skipped",
}


@dataclass
class IterationEvent:
    batch_id: str
    iteration: int
    total: int
    status: str
    detail: Optional[str] = None


@dataclass
class BatchCompleteEvent:
    batch_id: str
    passed: int
    total: int


class AlreadyRunningError(Exception):
    pass


@dataclass
class _Batch:
    id: str
    nodeid: str
    marker: str
    repeat_count: int
    events: "queue.Queue" = field(default_factory=queue.Queue)
    done: bool = False


def _latest_history_file(history_dir: Path) -> Optional[Path]:
    files = sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _find_test_result(history_file: Path, nodeid: str) -> Optional[dict]:
    data = json.loads(history_file.read_text())
    for test in data.get("tests", []):
        if test["nodeid"] == nodeid:
            return test
    return None


class TestRunner:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        history_dir: Optional[Path] = None,
        subprocess_run=subprocess.run,
    ):
        self._repo_root = repo_root
        self._history_dir = history_dir or (repo_root / "results" / "history")
        self._subprocess_run = subprocess_run
        self._lock = threading.Lock()
        self._active: Optional[_Batch] = None
        self._batches: dict[str, _Batch] = {}

    def start(self, nodeid: str, marker: str, repeat_count: int) -> str:
        with self._lock:
            if self._active is not None and not self._active.done:
                raise AlreadyRunningError(
                    "A test is already running — try again in a moment."
                )
            batch = _Batch(
                id=str(uuid.uuid4()), nodeid=nodeid, marker=marker, repeat_count=repeat_count
            )
            self._active = batch
            self._batches[batch.id] = batch
        thread = threading.Thread(target=self._run_batch, args=(batch,), daemon=True)
        thread.start()
        return batch.id

    def events(self, batch_id: str):
        """Blocking generator the SSE endpoint iterates — yields
        IterationEvents then one final BatchCompleteEvent."""
        batch = self._batches[batch_id]
        while True:
            item = batch.events.get()
            yield item
            if isinstance(item, BatchCompleteEvent):
                return

    def _run_batch(self, batch: _Batch) -> None:
        passed = 0
        for i in range(1, batch.repeat_count + 1):
            batch.events.put(IterationEvent(batch.id, i, batch.repeat_count, "running"))
            env = {**os.environ, "NETROPY_WEBAPP_BATCH_ID": batch.id}
            try:
                self._subprocess_run(
                    [sys.executable, "-m", "pytest", batch.nodeid, "-m", batch.marker],
                    cwd=self._repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                latest = _latest_history_file(self._history_dir)
                test_result = _find_test_result(latest, batch.nodeid) if latest else None
                if test_result is None:
                    status, detail = "error", "No result recorded for this run"
                else:
                    status = _OUTCOME_TO_STATUS.get(test_result["outcome"], "error")
                    detail = test_result.get("failure_message")
            except subprocess.TimeoutExpired:
                status, detail = "error", "Timed out after 10 minutes"
            except Exception as exc:
                status, detail = "error", str(exc)

            if status == "passed":
                passed += 1
            batch.events.put(IterationEvent(batch.id, i, batch.repeat_count, status, detail))

        batch.done = True
        with self._lock:
            if self._active is batch:
                self._active = None
        batch.events.put(BatchCompleteEvent(batch.id, passed, batch.repeat_count))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest --confcutdir=webapp webapp/tests/test_runner.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add webapp/runner.py webapp/tests/test_runner.py
git commit -m "feat(webapp): batch runner — one-at-a-time subprocess orchestration + live status"
```

---

### Task 8: `webapp/app.py` — FastAPI routes + SSE

**Files:**
- Create: `webapp/app.py`
- Test: `webapp/tests/test_app.py`

**Interfaces:**
- Consumes: `webapp.catalog.discover_groups`, `webapp.persistence.list_batches`, `webapp.runner.{TestRunner, AlreadyRunningError, IterationEvent, BatchCompleteEvent}`.
- Produces: `GET /api/modules`, `GET /api/catalog`, `POST /api/runs`, `GET /api/runs/{batch_id}/stream` (SSE), `GET /api/results`; static frontend at `/`; `results/` served at `/results/*`.

- [ ] **Step 1: Write the failing tests**

Create `webapp/tests/test_app.py`:

```python
"""Integration tests for the API surface using FastAPI's TestClient — no
real subprocess, no real pytest run. Run with:
    pytest --confcutdir=webapp webapp/tests/test_app.py -v
"""
from fastapi.testclient import TestClient

import webapp.app as app_module


def test_modules_endpoint_lists_traffic_generator_and_ten_future_modules():
    client = TestClient(app_module.app)
    data = client.get("/api/modules").json()
    assert len(data["modules"]) == 11
    assert data["modules"][0] == {
        "id": "traffic-generator",
        "name": "Traffic Generator",
        "available": True,
    }
    assert all(m["available"] is False for m in data["modules"][1:])


def test_catalog_endpoint_returns_real_groups():
    client = TestClient(app_module.app)
    data = client.get("/api/catalog").json()
    ids = {g["id"] for g in data["groups"]}
    assert "t1_auth" in ids


def test_unknown_nodeid_returns_404():
    client = TestClient(app_module.app)
    resp = client.post(
        "/api/runs", json={"nodeid": "tests/does/not/exist.py::nope", "repeat_count": 1}
    )
    assert resp.status_code == 404


def test_second_concurrent_run_returns_409(monkeypatch):
    import webapp.runner as runner_module

    class _AlwaysBusyRunner:
        def start(self, *a, **k):
            raise runner_module.AlreadyRunningError("busy")

    monkeypatch.setattr(app_module, "runner", _AlwaysBusyRunner())
    client = TestClient(app_module.app)
    groups = client.get("/api/catalog").json()["groups"]
    nodeid = groups[0]["files"][0]["tests"][0]["nodeid"]
    resp = client.post("/api/runs", json={"nodeid": nodeid, "repeat_count": 1})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest --confcutdir=webapp webapp/tests/test_app.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.app'` (or a `RuntimeError` about the missing `webapp/static/` directory — that's fine, Task 9 creates it; if that happens, `mkdir -p webapp/static && touch webapp/static/index.html` as a temporary stub before re-running, since Task 9 will overwrite it with the real one).

- [ ] **Step 3: Write the implementation**

Create `webapp/app.py`:

```python
"""FastAPI app: serves the dashboard's static frontend and its small API
— catalog, starting/streaming runs, and reading past results.

Launch with `python -m webapp.app` from the repo root (NOT
`python webapp/app.py` directly — that puts webapp/ itself on sys.path
instead of the repo root, and `from webapp.catalog import ...` would
fail to resolve `webapp` as a package).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webapp.catalog import discover_groups
from webapp.persistence import list_batches
from webapp.runner import AlreadyRunningError, IterationEvent, TestRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Netropy Test Dashboard")
runner = TestRunner()

FUTURE_MODULES = [
    "Session Strike", "RFC 2544", "RFC 9411", "AppPlayback", "DDoS Storm",
    "DNS Storm", "VoIP / SIP", "OTT Video", "ThreatStorm", "PQC",
]


class RunRequest(BaseModel):
    nodeid: str
    repeat_count: int = 1


@app.get("/api/modules")
def get_modules():
    return {
        "modules": [{"id": "traffic-generator", "name": "Traffic Generator", "available": True}]
        + [
            {
                "id": name.lower().replace(" ", "-").replace("/", ""),
                "name": name,
                "available": False,
            }
            for name in FUTURE_MODULES
        ]
    }


@app.get("/api/catalog")
def get_catalog():
    groups = discover_groups()
    return {
        "groups": [
            {
                "id": g.id,
                "label": g.label,
                "run_all_nodeids": g.run_all_nodeids,
                "files": [
                    {
                        "path": f.path,
                        "short_description": f.short_description,
                        "full_description": f.full_description,
                        "tests": [
                            {
                                "nodeid": t.nodeid,
                                "name": t.name,
                                "markers": t.markers,
                                "safety_marker": t.safety_marker,
                            }
                            for t in f.tests
                        ],
                    }
                    for f in g.files
                ],
            }
            for g in groups
        ]
    }


def _marker_for(nodeid: str) -> str:
    for g in discover_groups():
        for f in g.files:
            for t in f.tests:
                if t.nodeid == nodeid:
                    return t.safety_marker or "hardware_free"
    raise HTTPException(404, f"Unknown test: {nodeid}")


@app.post("/api/runs")
def start_run(req: RunRequest):
    marker = _marker_for(req.nodeid)
    try:
        batch_id = runner.start(req.nodeid, marker, req.repeat_count)
    except AlreadyRunningError as exc:
        raise HTTPException(409, str(exc))
    return {"batch_id": batch_id}


def _sse_format(event) -> str:
    if isinstance(event, IterationEvent):
        payload = {
            "type": "iteration",
            "iteration": event.iteration,
            "total": event.total,
            "status": event.status,
            "detail": event.detail,
        }
    else:
        payload = {"type": "batch_complete", "passed": event.passed, "total": event.total}
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/api/runs/{batch_id}/stream")
def stream_run(batch_id: str):
    def generate():
        for event in runner.events(batch_id):
            yield _sse_format(event)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/results")
def get_results():
    batches = list_batches()
    return {
        "batches": [
            {
                "batch_id": b.batch_id,
                "nodeid": b.nodeid,
                "started_at": b.started_at,
                "pass_count": b.pass_count,
                "total": len(b.iterations),
                "total_duration": b.total_duration,
                "iterations": [
                    {
                        "run_id": i.run_id,
                        "timestamp": i.timestamp,
                        "outcome": i.outcome,
                        "duration": i.duration,
                        "failure_message": i.failure_message,
                        "screenshot": i.screenshot,
                        "trace": i.trace,
                    }
                    for i in b.iterations
                ],
            }
            for b in batches
        ]
    }


# Order matters: specific mounts before the catch-all "/" static mount.
app.mount("/results", StaticFiles(directory=str(REPO_ROOT / "results")), name="results")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webapp.app:app", host="127.0.0.1", port=8765, reload=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest --confcutdir=webapp webapp/tests/test_app.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add webapp/app.py webapp/tests/test_app.py
git commit -m "feat(webapp): FastAPI app — catalog/runs/results API + SSE"
```

---

### Task 9: Frontend shell — tabs, coming-soon states, page nav

**Files:**
- Create: `webapp/static/index.html`
- Create: `webapp/static/styles.css`
- Create: `webapp/static/app.js` (initial version — module tabs + page nav only; Tasks 10-12 extend this same file)

**Interfaces:**
- Consumes: `GET /api/modules` (Task 8).
- Produces: DOM elements later tasks attach to — `#module-tabs`, `#module-panel`, `#nav-tests`, `#nav-results`.

- [ ] **Step 1: Create the HTML shell**

Create `webapp/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Netropy Test Dashboard</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="topbar">
    <img src="/static/apposite-logo.png" alt="Apposite Technologies" class="logo">
    <h1>Netropy Test Dashboard</h1>
  </header>

  <nav class="tabs" id="module-tabs"></nav>

  <div class="page-nav">
    <button type="button" id="nav-tests" class="page-nav-btn active">Tests</button>
    <button type="button" id="nav-results" class="page-nav-btn">Results</button>
  </div>

  <main id="module-panel"></main>

  <div id="run-modal" class="modal-overlay" hidden>
    <div class="modal">
      <button type="button" class="modal-close" id="run-modal-close">&times;</button>
      <h2>Run test</h2>
      <p id="run-modal-warning" class="stateful-warning" hidden>
        ⚠ This generates real network traffic on the lab hardware.
      </p>
      <label class="field">
        How many times?
        <input type="number" id="run-modal-count" min="1" value="1">
      </label>
      <button type="button" id="run-modal-confirm" class="btn-primary">Run</button>
    </div>
  </div>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create the stylesheet**

Note: this references `webapp/DESIGN.md`'s tokens from Task 1 verbatim.

Create `webapp/static/styles.css`:

```css
:root {
  --bg: #EEF2F8;
  --surface: #FFFFFF;
  --surface-2: #F5F7FB;
  --border: #DCE3EE;
  --ink: #16294A;
  --ink-dim: #6B7686;
  --accent: #1D4E8F;
  --accent-hover: #16406F;
  --ok: #1F8A4C;
  --ok-bg: #E3F5E9;
  --warn: #8A6D1F;
  --warn-bg: #FDF3D8;
  --bad: #C23B3B;
  --bad-bg: #FBEAEA;
  --muted: #9AA3B0;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Inter", -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.topbar .logo { height: 28px; }
.topbar h1 { font-size: 16px; font-weight: 600; margin: 0; }

.tabs {
  display: flex;
  gap: 4px;
  padding: 0 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}
.tab {
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-dim);
  border: none;
  background: none;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

main { max-width: 960px; margin: 0 auto; padding: 24px; }

.coming-soon {
  text-align: center;
  padding: 60px 20px;
  color: var(--ink-dim);
}
.coming-soon .lock { font-size: 32px; opacity: 0.4; margin-bottom: 8px; }

.page-nav {
  display: flex; gap: 8px; padding: 12px 24px 0; max-width: 960px; margin: 0 auto;
}
.page-nav-btn {
  padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--surface); color: var(--ink-dim); font-weight: 600; cursor: pointer;
}
.page-nav-btn.active { color: var(--accent); border-color: var(--accent); }

.group { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 16px; overflow: hidden; }
.group-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; background: var(--surface-2); border-bottom: 1px solid var(--border);
}
.group-header h2 { font-size: 14px; margin: 0; }

.test-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border); cursor: pointer;
}
.test-row:last-child { border-bottom: none; }
.test-row:hover { background: var(--surface-2); }
.test-name { font-weight: 600; }
.test-desc { color: var(--ink-dim); font-size: 13px; margin-top: 2px; }

.pill { display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 600; }
.pill-ok { background: var(--ok-bg); color: var(--ok); }
.pill-warn { background: var(--warn-bg); color: var(--warn); }
.pill-bad { background: var(--bad-bg); color: var(--bad); }

.btn-primary {
  background: var(--accent); color: white; border: none; border-radius: 6px;
  padding: 6px 16px; font-weight: 600; cursor: pointer;
}
.btn-primary:hover { background: var(--accent-hover); }
.btn-outline {
  background: transparent; border: 1px solid var(--border); color: var(--ink);
  border-radius: 6px; padding: 6px 16px; font-weight: 600; cursor: pointer;
}

.detail-panel { padding: 12px 16px; background: var(--surface-2); border-bottom: 1px solid var(--border); font-size: 13px; white-space: pre-wrap; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(10,20,40,0.35);
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
.modal {
  background: var(--surface); border-radius: 12px; padding: 24px; width: 360px;
  box-shadow: 0 10px 40px rgba(15,30,60,0.18); position: relative;
}
.modal-close { position: absolute; top: 12px; right: 12px; background: none; border: none; font-size: 18px; cursor: pointer; color: var(--ink-dim); }
.stateful-warning { background: var(--warn-bg); color: var(--warn); padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; }
.field { display: block; font-size: 13px; font-weight: 600; margin-bottom: 16px; }
.field input {
  display: block; width: 100%; margin-top: 6px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 6px; font-size: 14px;
}
.field input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(29,78,143,0.15); }

.results-table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.results-table th {
  text-align: left; font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--ink-dim); background: var(--surface-2); padding: 10px 12px; border-bottom: 1px solid var(--border);
}
.results-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.iteration-dots { display: inline-flex; gap: 3px; }
.iteration-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.iteration-dot.pass { background: var(--ok); }
.iteration-dot.fail { background: var(--bad); }
.iteration-dot.error { background: var(--muted); }

[hidden] { display: none !important; }
```

- [ ] **Step 3: Create `app.js` (tabs + page nav only for now)**

Create `webapp/static/app.js`:

```js
const state = { catalog: null, liveStatus: {} };

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function loadModules() {
  const { modules } = await fetchJSON("/api/modules");
  const nav = document.getElementById("module-tabs");
  nav.hidden = false;
  nav.innerHTML = "";
  modules.forEach((m, i) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (i === 0 ? " active" : "");
    btn.textContent = m.name;
    btn.addEventListener("click", () => selectModule(m, btn));
    nav.appendChild(btn);
  });
  selectModule(modules[0], nav.firstElementChild);
}

function selectModule(module, btn) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  btn.classList.add("active");
  const panel = document.getElementById("module-panel");
  if (!module.available) {
    panel.innerHTML = `
      <div class="coming-soon">
        <div class="lock">&#128274;</div>
        <h2>${module.name}</h2>
        <p>Test coverage for this module hasn't been built yet.</p>
      </div>`;
    return;
  }
  renderTrafficGenerator(panel);
}

async function renderTrafficGenerator(panel) {
  panel.innerHTML = "<p>Loading tests…</p>";
  // Task 10 fills this in.
}

document.getElementById("nav-tests").addEventListener("click", () => showPage("tests"));
document.getElementById("nav-results").addEventListener("click", () => showPage("results"));

function showPage(page) {
  document.getElementById("nav-tests").classList.toggle("active", page === "tests");
  document.getElementById("nav-results").classList.toggle("active", page === "results");
  const tabs = document.getElementById("module-tabs");
  if (page === "results") {
    tabs.hidden = true;
    document.getElementById("module-panel").innerHTML = "<p>Results page — Task 12.</p>";
  } else {
    tabs.hidden = false;
    loadModules();
  }
}

loadModules();
```

- [ ] **Step 4: Manual verification**

```bash
python -m webapp.app
```
Open `http://127.0.0.1:8765/` in a browser. Expected: header with logo, 11 tabs (Traffic Generator active/first, 10 others), clicking any of the 10 others shows the "coming soon" empty state with that module's real name, clicking back to Traffic Generator shows "Loading tests…". Stop the server (Ctrl+C).

- [ ] **Step 5: Commit**

```bash
git add webapp/static/
git commit -m "feat(webapp): frontend shell — module tabs, coming-soon states, page nav"
```

---

### Task 10: Frontend — test browsing + detail view

**Files:**
- Modify: `webapp/static/app.js` (fills in `renderTrafficGenerator`, adds group/test rendering)
- Modify: `webapp/static/styles.css` (none expected beyond Task 9's — reuse existing classes)

**Interfaces:**
- Consumes: `GET /api/catalog` (Task 8).

- [ ] **Step 1: Replace `renderTrafficGenerator` and add rendering helpers**

In `webapp/static/app.js`, replace the `renderTrafficGenerator` function and everything below it (before `loadModules();` at the bottom) with:

```js
async function renderTrafficGenerator(panel) {
  panel.innerHTML = "<p>Loading tests…</p>";
  const { groups } = await fetchJSON("/api/catalog");
  state.catalog = groups;
  panel.innerHTML = groups.map(renderGroup).join("");
  attachTestRowHandlers();
}

function renderGroup(group) {
  const rows = group.files
    .flatMap((f) => f.tests.map((t) => renderTestRow(t, f)))
    .join("");
  return `
    <section class="group" data-group-id="${group.id}">
      <div class="group-header">
        <h2>${group.label}</h2>
        <button type="button" class="btn-outline run-all-btn" data-nodeids='${JSON.stringify(group.run_all_nodeids)}'>
          Run all in ${group.label.split(" — ")[0]}
        </button>
      </div>
      ${rows}
    </section>`;
}

function safetyPill(marker) {
  if (marker === "stateful") return `<span class="pill pill-warn">Generates traffic</span>`;
  return `<span class="pill pill-ok">Safe</span>`;
}

function renderTestRow(test, file) {
  return `
    <div class="test-row" data-nodeid="${test.nodeid}" data-full-description="${escapeAttr(file.full_description)}">
      <div>
        <div class="test-name">${test.name}</div>
        <div class="test-desc">${file.short_description}</div>
      </div>
      <div style="display:flex; align-items:center; gap:10px;">
        <span class="pill" data-status-for="${test.nodeid}"></span>
        ${safetyPill(test.safety_marker)}
        <button type="button" class="btn-primary run-btn" data-nodeid="${test.nodeid}" data-marker="${test.safety_marker}">Run</button>
      </div>
    </div>`;
}

function escapeAttr(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function attachTestRowHandlers() {
  document.querySelectorAll(".test-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest(".run-btn")) return;
      toggleDetail(row);
    });
  });
  document.querySelectorAll(".run-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openRunModal(btn.dataset.nodeid, btn.dataset.marker);
    });
  });
  document.querySelectorAll(".run-all-btn").forEach((btn) => {
    btn.addEventListener("click", () => runAllInGroup(JSON.parse(btn.dataset.nodeids)));
  });
}

function toggleDetail(row) {
  const existing = row.nextElementSibling;
  if (existing && existing.classList.contains("detail-panel")) {
    existing.remove();
    return;
  }
  document.querySelectorAll(".detail-panel").forEach((p) => p.remove());
  const panel = document.createElement("div");
  panel.className = "detail-panel";
  panel.textContent = row.dataset.fullDescription;
  row.after(panel);
}
```

(Leave `openRunModal` and `runAllInGroup` as forward references for now —
Task 11 defines them. `loadModules();` stays as the last line of the
file.)

- [ ] **Step 2: Manual verification**

```bash
python -m webapp.app
```
Open the browser, click Traffic Generator (or it's already active). Expected: groups render matching the real `tests/` directory (T1 — Auth, T2 — Dashboard, ... T10/T12 — Lifecycle, etc.), each test row shows its short description and a "Safe"/"Generates traffic" pill correctly per its marker, clicking a row (not its Run button) expands the full docstring below it and clicking again collapses it, clicking a different row's Run button doesn't yet do anything (expected — Task 11). Stop the server.

- [ ] **Step 3: Commit**

```bash
git add webapp/static/app.js
git commit -m "feat(webapp): frontend test browsing — groups, rows, detail expand"
```

---

### Task 11: Frontend — run flow + live status

**Files:**
- Modify: `webapp/static/app.js` (adds `openRunModal`, `startRun`, `streamRun`, `runAllInGroup`, wires the modal buttons)

**Interfaces:**
- Consumes: `POST /api/runs`, `GET /api/runs/{batch_id}/stream` (Task 8).

- [ ] **Step 1: Add the run-flow functions**

In `webapp/static/app.js`, add this block right after `attachTestRowHandlers`/`toggleDetail` (before `loadModules();` at the bottom):

```js
let modalNodeid = null;

function openRunModal(nodeid, marker) {
  modalNodeid = nodeid;
  document.getElementById("run-modal-warning").hidden = marker !== "stateful";
  document.getElementById("run-modal-count").value = 1;
  document.getElementById("run-modal").hidden = false;
}

document.getElementById("run-modal-close").addEventListener("click", () => {
  document.getElementById("run-modal").hidden = true;
});

document.getElementById("run-modal-confirm").addEventListener("click", async () => {
  const count = parseInt(document.getElementById("run-modal-count").value, 10) || 1;
  document.getElementById("run-modal").hidden = true;
  await startRun(modalNodeid, count);
});

async function startRun(nodeid, repeatCount) {
  try {
    const { batch_id } = await fetchJSON("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nodeid, repeat_count: repeatCount }),
    });
    streamRun(batch_id, nodeid);
  } catch (err) {
    alert(err.message);
  }
}

function statusPillClass(status) {
  if (status === "passed") return "pill-ok";
  if (status === "failed" || status === "error") return "pill-bad";
  return "pill-warn";
}

function streamRun(batchId, nodeid) {
  const el = document.querySelector(`[data-status-for="${nodeid}"]`);
  state.liveStatus[nodeid] = "running";
  const source = new EventSource(`/api/runs/${batchId}/stream`);
  source.onmessage = (e) => {
    const payload = JSON.parse(e.data);
    if (payload.type === "iteration") {
      if (el) {
        el.textContent = `${payload.status} (${payload.iteration}/${payload.total})`;
        el.className = "pill " + statusPillClass(payload.status);
      }
    } else if (payload.type === "batch_complete") {
      state.liveStatus[nodeid] = "done";
      if (el) el.textContent = `${payload.passed}/${payload.total} passed`;
      source.close();
    }
  };
  source.onerror = () => {
    source.close();
    state.liveStatus[nodeid] = "done";
  };
}

async function runAllInGroup(nodeids) {
  for (const nodeid of nodeids) {
    await startRun(nodeid, 1);
    await new Promise((resolve) => {
      const check = setInterval(() => {
        if (state.liveStatus[nodeid] === "done") {
          clearInterval(check);
          resolve();
        }
      }, 300);
    });
  }
}
```

- [ ] **Step 2: Manual verification — hardware_free path**

```bash
python -m webapp.app
```
In the browser: pick a `hardware_free` test (e.g. anything in T2 — Dashboard), click Run, confirm no stateful warning shows, enter repeat count `1`, confirm. Expected: the pill next to that row updates live through `running (1/1)` to a final `passed`/`failed` state within a few seconds, matching what running it by hand (`pytest <nodeid> -m hardware_free`) would show. Try repeat count `3` on a different `hardware_free` test and confirm it cycles through 3 iterations before showing a final count.

- [ ] **Step 3: Manual verification — stateful path (requires explicit go-ahead from Logan before running any stateful test)**

Pick a `stateful` test, click Run — confirm the warning notice appears in the modal before confirming. Confirm with repeat count 1. While it's running, open a second browser tab and try to Run a different test — confirm it's rejected with the "already running" message (`alert()` box), not silently queued. Wait for the first to finish and confirm the second can then be started normally.

- [ ] **Step 4: Commit**

```bash
git add webapp/static/app.js
git commit -m "feat(webapp): frontend run flow — repeat-count modal, stateful warning, live SSE status"
```

---

### Task 12: Frontend — Results page

**Files:**
- Modify: `webapp/static/app.js` (implements the `showPage("results")` branch)

**Interfaces:**
- Consumes: `GET /api/results` (Task 8).

- [ ] **Step 1: Implement the Results page renderer**

In `webapp/static/app.js`, replace the `showPage` function's `results` branch body
(currently `document.getElementById("module-panel").innerHTML = "<p>Results page — Task 12.</p>";`)
with a call to a new `renderResults(panel)` function, and add that function plus its row helper anywhere above `loadModules();`:

```js
function showPage(page) {
  document.getElementById("nav-tests").classList.toggle("active", page === "tests");
  document.getElementById("nav-results").classList.toggle("active", page === "results");
  const tabs = document.getElementById("module-tabs");
  const panel = document.getElementById("module-panel");
  if (page === "results") {
    tabs.hidden = true;
    renderResults(panel);
  } else {
    tabs.hidden = false;
    loadModules();
  }
}

async function renderResults(panel) {
  panel.innerHTML = "<p>Loading results…</p>";
  const { batches } = await fetchJSON("/api/results");
  if (batches.length === 0) {
    panel.innerHTML = `<p class="test-desc">No runs yet — go run a test from the Tests page.</p>`;
    return;
  }
  panel.innerHTML = `
    <table class="results-table">
      <thead><tr><th>Test</th><th>Runs</th><th>Pass rate</th><th>Duration</th><th>Started</th><th>Artifacts</th></tr></thead>
      <tbody>${batches.map(renderResultRow).join("")}</tbody>
    </table>`;
}

function renderResultRow(batch) {
  const dots = batch.iterations
    .map(
      (i) =>
        `<span class="iteration-dot ${i.outcome === "pass" ? "pass" : i.outcome === "error" ? "error" : "fail"}"></span>`
    )
    .join("");
  const links =
    batch.iterations
      .flatMap((i) => [
        i.screenshot ? `<a href="/results/${i.screenshot}" target="_blank">screenshot</a>` : null,
        i.trace ? `<a href="/results/${i.trace}" target="_blank">trace</a>` : null,
      ])
      .filter(Boolean)
      .join(" · ") || "—";
  return `
    <tr>
      <td>${batch.nodeid.split("::").pop()}</td>
      <td><span class="iteration-dots">${dots}</span></td>
      <td>${batch.pass_count}/${batch.total}</td>
      <td>${batch.total_duration.toFixed(1)}s</td>
      <td>${batch.started_at.replace("T", " ").replace("Z", " UTC")}</td>
      <td>${links}</td>
    </tr>`;
}
```

(Note the `/results/${i.screenshot}` and `/results/${i.trace}` links —
these rely on Task 8's `app.mount("/results", StaticFiles(directory=str(REPO_ROOT / "results")), ...)`,
since the stored paths in history JSON are already relative to `results/`,
e.g. `"artifacts/tests-.../test-failed-1.png"`.)

- [ ] **Step 2: Manual verification**

```bash
python -m webapp.app
```
Run a couple of tests from the Tests page (per Task 11's verification), then click the Results tab. Expected: one row per batch (most recent first), correct pass/total count, a row of small colored dots matching each iteration's outcome, a duration, a timestamp, and (for any failed iteration) working screenshot/trace links that open the actual artifact. Confirm the page persists correctly after restarting the server (`Ctrl+C` then `python -m webapp.app` again, revisit Results) — results survive because they're just reading `results/history/`, not any in-memory state.

- [ ] **Step 3: Commit**

```bash
git add webapp/static/app.js
git commit -m "feat(webapp): frontend Results page — batch-grouped table with artifact links"
```

---

### Task 13: `webapp/README.md` + end-to-end verification

**Files:**
- Create: `webapp/README.md`

- [ ] **Step 1: Write the README**

Create `webapp/README.md`:

```markdown
# Netropy Test Dashboard

A local, browser-based dashboard for browsing and running this repo's
Playwright tests — no terminal, no pytest/Playwright knowledge needed.

## Run it

    make run-dashboard

(or `python -m webapp.app` from the repo root — not `python webapp/app.py`
directly, see the comment in `app.py`.) Then open the URL it prints
(`http://127.0.0.1:8765/`).

## What it does

- **Tests** tab: browse tests grouped exactly the way `tests/` is
  organized on disk, click a test to see its full description, click
  Run to execute it for real (prompts for a repeat count; a `stateful`
  test warns it generates real traffic before starting).
- **Results** tab: every run's history, persisted in `results/history/`
  (the same files the plain CLI-driven suite and `results/index.html`
  already use) — survives restarts.
- Exactly one test runs at a time, globally, enforced server-side.

## Design

See `DESIGN.md` for the color/type/component tokens this UI is built
from (matched to the real Netropy Traffic Generator UI, not invented).

## Backend tests

    pytest --confcutdir=webapp webapp/tests/ -v

(`--confcutdir=webapp` keeps this from picking up the repo-root
`conftest.py`, which is for the real Playwright suite and would
otherwise try to write a spurious `results/history` entry for these
fast unit tests too.)
```

- [ ] **Step 2: Full end-to-end manual verification checklist**

```bash
source .venv/bin/activate
pytest --confcutdir=webapp webapp/tests/ -v
```
Expected: all backend unit tests pass (catalog, persistence, runner, app — from Tasks 3-8).

```bash
python -m webapp.app
```
In the browser, confirm all of:
- [ ] All 11 tabs render; 10 show "coming soon" with the correct module name; Traffic Generator is populated.
- [ ] Every group under Traffic Generator matches a real `tests/` subdirectory — no invented names, no combined `_all.py` files listed as separate tests, no quarantined tests visible.
- [ ] Clicking a test row expands its full docstring; clicking again collapses it.
- [ ] Running a `hardware_free` test at repeat count 1 shows live status through to a final result.
- [ ] Running the same test at repeat count 3 runs all 3 iterations even if one fails partway (don't force a failure — just confirm the count).
- [ ] A `stateful` test's Run modal shows the traffic warning; a second Run attempt while one is active is rejected, not queued.
- [ ] The Results page shows a correctly-grouped row per batch with working artifact links for any failure.
- [ ] Closing the browser tab mid-run and reopening `http://127.0.0.1:8765/` doesn't lose the in-progress run — the batch keeps running server-side and the Results page reflects it once done.

```bash
# Confirm the existing suite and dashboard are completely unaffected:
python -m pytest -m hardware_free tests/t2_dashboard/ -q
python scripts/build_report.py
```
Expected: both succeed exactly as they did before this project — this new app is additive, not a replacement.

- [ ] **Step 3: Commit**

```bash
git add webapp/README.md
git commit -m "docs(webapp): README + end-to-end verification"
```

---

## Self-Review

**Spec coverage:** Module tabs (Task 8's `FUTURE_MODULES` + Task 9) ✓. Test browsing grouped by repo convention (Task 3, 10) ✓. Click-for-detail (Task 10) ✓. Run + repeat count + stateful warning + live streaming (Task 7, 8, 11) ✓. One-at-a-time enforcement (Task 7) ✓. Results page persisting via existing history format (Task 6, 8, 12) ✓. Artifacts — screenshots (already worked, Task 6 just adds the read-side `trace` field) + traces (Task 5) ✓. Design system extraction (Task 1) used throughout (Task 9) ✓. No Node/build step anywhere ✓.

**Placeholder scan:** No TBD/TODO/"add appropriate X" found — every step has real, complete code or an exact command.

**Type consistency:** Checked across tasks — `TestEntry`/`TestFile`/`TestGroup` (Task 3) field names match their exact usage in `app.py` (Task 8) and `app.js` (Task 10). `IterationEvent`/`BatchCompleteEvent` (Task 7) field names match `_sse_format` (Task 8) and the `payload.type`/`payload.status` shape `app.js` (Task 11) expects. `IterationResult`/`BatchResult` (Task 6) field names match the `/api/results` response shape (Task 8) and `renderResultRow` (Task 12). `NETROPY_WEBAPP_BATCH_ID` is the one env var name used consistently in `runner.py` (Task 7), `conftest.py` (Task 5), and `collect_run.py` (Task 4).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-10-test-runner-webapp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
