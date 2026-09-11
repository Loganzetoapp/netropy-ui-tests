# Local Test Runner Web App — Design Spec

Date: 2026-09-10
Status: approved by Logan (chat), pending written-spec review

## Purpose

A local, browser-based dashboard that lets a non-technical user browse this
repo's Playwright UI tests, run one with a click, watch it go, and check
results — without ever touching a terminal or knowing what pytest or
Playwright are. Nothing here changes how the test suite itself works; this
is a new, separate control surface on top of it.

## Scope

In scope: browsing/running tests in the existing suite, live run status,
a persistent results view, visual styling matched to Apposite's Netropy UI.
Out of scope (this pass): editing test code, writing new tests from the UI,
CI integration, remote/multi-machine access (this is a `localhost`-only
tool), auth (single local user, same trust boundary as running pytest by
hand).

## Module tabs

Top-level navigation is one tab per Netropy product module, taken directly
from the product's own "Create Testbed" module picker (screenshot provided
2026-09-10) — not invented:

- **Traffic Generator** — populated now; wraps this repo's existing test suite.
- Session Strike, RFC 2544, RFC 9411, AppPlayback, DDoS Storm, DNS Storm,
  VoIP / SIP, OTT Video, ThreatStorm, PQC — all render as a clean
  "coming soon" empty state (icon + module name + one line: "Test coverage
  for this module hasn't been built yet.").

Tabs are a static list for now (11 entries, one real). No mechanism needed
to add tabs dynamically — that's a future problem for whenever a second
module gets real coverage.

## Test discovery ("catalog")

Tests are discovered by **statically parsing the AST** of every
`tests/*/test_*.py` file — no pytest invocation needed just to list them
(fast, zero side effects, can't accidentally reserve a port or touch the
box just by opening the browser).

For each file:
- **Group**: derived mechanically from its parent directory name. Split on
  `_`; the leading `t<N>` (or `t<N>_t<M>`-style, e.g. `t10_t12`) token(s)
  become the numeric prefix, the rest is title-cased for the label.
  `t1_auth` → "T1 — Auth", `t10_t12_lifecycle` → "T10/T12 — Lifecycle".
  This is fully mechanical — a future `tests/t14_x/` directory groups
  itself correctly with zero code changes here.
- **Short description**: first line of the module's docstring (the
  existing `"""T<N> — <one-liner>` convention every test file already
  follows).
- **Full description**: the complete module docstring, shown in the
  click-to-expand detail view.
- **Test entries**: every `def test_*(...)` in the file, with its
  `@pytest.mark.*` decorators read to determine `hardware_free` /
  `stateful` / `smoke` / `quarantine` / `xfail`.
- **Combined-suite files are excluded from the browsable list.** Files
  like `test_t1_auth_all.py` just re-run the same scenarios as their
  standalone sibling files in one session (per their own docstrings) —
  showing both would look like duplicate tests to someone who doesn't know
  why. Detection has to be precise, not a loose `_all.py` suffix check:
  caught one real false positive during spec review —
  `test_t7_frame_size_apply_to_all.py` also ends in `_all.py` but is a
  genuinely distinct test ("apply to all" is part of its actual name, not
  the combined-suite convention) and must stay visible. The actual rule:
  a file is a combined-suite file only if its name, stripped of the
  `test_`/`.py` wrapper, is *exactly* `"<directory name>_all"` —
  `t1_auth` → `test_t1_auth_all.py` matches; `t7_streams` →
  `test_t7_frame_size_apply_to_all.py` does not (`"t7_frame_size_apply_to"
  != "t7_streams"`) and stays in the list. Confirmed against every
  `_all.py` file currently in the repo (`t1_auth`, `t2_dashboard`,
  `t3_port_management` match the combined-suite shape; the T7 one
  doesn't).
- **Quarantined tests are excluded** from the default browsing list
  entirely (matches `pytest.ini`'s `-m "not quarantine"` default) — a
  known-flaky test showing up as a normal, clickable "Run" target would
  mislead a non-technical user about its reliability.

Each group additionally gets a **"Run all in T&lt;N&gt;"** action (runs every
test in that group's real files sequentially, once each — no repeat-count
prompt) — this is the UI's replacement for the hidden combined-suite
files' purpose, not a new capability. Repeats are a per-test stability
tool; a group's "run all" is a quick full-area check, not a stability run.

## Test detail view

Clicking a test (not its Run button) expands an inline panel or opens a
lightweight modal showing: the full module docstring, its file path, its
marker(s) rendered as plain-language badges ("Safe — no traffic" for
`hardware_free`, "Generates real traffic" for `stateful`), and its Run
button (same action as the list-row button, just also reachable here).

## Running a test

1. Click **Run** → a small prompt asks "How many times?" (numeric input,
   default 1, minimum 1). No other configuration is ever asked for.
2. **If the test is `stateful`**, the same prompt shows a plain-language
   notice above the count field: *"This generates real network traffic on
   the lab hardware."* — no jargon, no acronyms, just the fact. Confirming
   proceeds; there's no separate second dialog.
3. Backend starts a **batch**: `repeat_count` sequential pytest
   invocations of that one test's nodeid (`pytest <nodeid> -m <marker(s)
   on that test> --headed=false`), each its own full pytest session (so
   the existing `conftest.py` `pytest_sessionfinish` hook writes a normal
   `results/history/<run-id>.json` entry for each one, unchanged). **All
   `repeat_count` iterations always run, even if an earlier one fails** —
   this matches the existing "Stability run" convention in CLAUDE.md
   (`for i in {1..5}; do pytest ...; done`, which never stops early
   either); the whole point of a repeat count is seeing the full
   pass/fail pattern, not stopping at the first surprise.
4. **Exactly one batch runs at a time, globally**, enforced by a simple
   in-process lock in the backend — satisfies CLAUDE.md's "never run
   stateful tests in parallel" by construction, and avoids two people
   fighting over the same hardware from two browser tabs. A second Run
   attempt while one is active gets a clear "A test is already running —
   try again in a moment" response, not a silent queue.
5. Live status streams to the browser over **Server-Sent Events** (one-way
   push — matches "queued/running/passed/failed," no need for
   full-duplex WebSockets): each iteration transitions
   `queued → running → passed | failed | error`, plus a final
   `batch_complete` event once all `repeat_count` iterations finish.
   - `failed` = pytest ran and the test's own assertions failed.
   - `error` = the run itself didn't complete cleanly (crash, timeout, box
     unreachable) — kept visually distinct so "the product failed the
     test" and "the run itself broke" never look the same to a
     non-technical user.
6. **A browser tab closing mid-run never aborts the run.** The pytest
   subprocess is server-owned, not tied to the SSE connection — closing
   the tab (or a flaky connection) just stops that client's live view;
   the batch keeps running to completion server-side (this matters most
   for `stateful` tests already mid-activation, where an abrupt kill
   would skip teardown). Reopening the Results page shows whatever
   completed in the meantime.

## Results page

Reads `results/history/*.json` — **the same file this repo's existing
static dashboard (`scripts/build_report.py`) already writes to and reads
from** — so nothing new is invented for persistence, and results already
survive restarts/sessions for free.

One small, additive, backward-compatible schema extension: a run
triggered from this web app tags its history entry with
`"batch_id": "<uuid>"` (via an env var `NETROPY_WEBAPP_BATCH_ID` that
`collect_run.py` picks up if set, else the field is simply absent —
existing CLI-triggered history entries are untouched). The Results page
groups entries by `batch_id` into one row per logical "Run": test name,
repeat count, pass/fail per iteration (as a sparkline-style sequence,
reusing the visual idea already built for the stability dashboard),
total duration, timestamp, and links to any artifact (screenshot/trace)
each iteration has.

## Artifacts

Screenshots-on-failure already work end-to-end (fixed earlier this
session) and are already linked in the history JSON. **Traces are not
currently captured at all.** Proposal: enable Playwright tracing
(`retain-on-failure`) **only for runs this web app triggers**, via the
same `NETROPY_WEBAPP_BATCH_ID`-gated code path — the existing CLI-driven
suite's behavior and disk usage stay exactly as they are today. Trace
path gets a new `"trace"` field in the history schema, same pattern as
`"screenshot"`. A trace link opens instructions to run
`playwright show-trace <path>` (there's no bundled in-browser trace
viewer in this design — that's its own tool with its own UI; linking out
to the standard one is enough for v1).

## Design system

Visual language extracted from the two screenshots provided (main
dashboard, Create Testbed modal) plus the Apposite logo file — palette,
typography, button styles (primary/disabled/outline), status pill
shapes, card/table chrome, modal chrome, tooltip style. Written to
`webapp/DESIGN.md` as the source of truth before any UI code is written.
Explicitly **not** a literal recreation of Netropy's specific screens
(no Port Status table, no CPU/memory gauges) — this app's own views
(tabs, test list, run modal, results table) are shaped around what it
actually needs, styled with Netropy's theme. The `frontend-design` skill
is used to execute this existing system with polish, not to invent a new
direction.

## Architecture

```
webapp/
  app.py            # FastAPI app: routes + SSE endpoint
  runner.py         # subprocess orchestration, one-batch-at-a-time lock,
                     # per-iteration status tracking
  catalog.py         # AST-based test discovery (see "Test discovery" above)
  persistence.py     # reads results/history/*.json for the Results page
  static/
    index.html, app.js, styles.css, apposite-logo.svg
  DESIGN.md
  README.md          # how to launch, one command
```

New Python deps: `fastapi`, `uvicorn` (added to `requirements.txt`).
Frontend: vanilla HTML/CSS/JS, no Node, no npm, no build step — launching
this app is `python webapp/app.py` (or a `make run-dashboard` convenience
target), then open the browser it prints.

### API surface (for the implementation plan to build against)
- `GET /api/catalog` → modules → (for traffic-generator) groups → tests,
  shaped per "Test discovery" above.
- `POST /api/runs` `{nodeid, repeat_count}` → `{batch_id}` (409 if a batch
  is already active).
- `GET /api/runs/{batch_id}/stream` → SSE: per-iteration status events +
  final `batch_complete`.
- `GET /api/results` → history entries grouped by `batch_id` for the
  Results page.

## Error handling

- Pytest subprocess crash / box unreachable / timeout before junit.xml is
  written → surfaced as `error` (distinct from `failed`), never a hung
  spinner. `runner.py` applies a generous but finite timeout per iteration.
- Concurrent run attempts → `409` with a plain-language message, no
  silent queueing.
- SSE disconnect → run continues server-side regardless (see above);
  reconnecting or checking Results shows current/final state.
- Malformed/missing history JSON on the Results page → skipped with a
  warning, same defensive pattern already used in `build_report.py`
  (never crash the page over one bad file).

## Testing / verification

No existing automated coverage needs to change. For this new app itself:
backend logic worth unit-testing in isolation (catalog AST parsing,
batch/lock state transitions in `runner.py`) — normal TDD as it's built.
End-to-end verification is manual, by hand, once built: launch the app,
confirm all 11 tabs render (10 as "coming soon"), browse Traffic
Generator's groups against the actual `tests/` directory for an exact
match, run one `hardware_free` test at repeat count 1 and 3 and watch
live status update correctly, run one `stateful` test and confirm the
warning copy appears and a second concurrent attempt is rejected, confirm
the Results page shows a correctly-grouped batch with working artifact
links, and confirm nothing about this new app touches or breaks the
existing `pytest -m hardware_free` CLI workflow or the existing
`results/index.html` static dashboard.

## Known v1 simplification

`xfail`-marked tests (currently 2 in the whole suite) aren't given special
treatment — an xfail test that fails as expected will show as a plain
"failed" iteration rather than a distinguished "failed as expected" state.
Handling this properly needs junit's xfail/xpass outcome types added to
`collect_run.py`'s parser, which only recognizes
pass/fail/error/skip today. Low-impact at 2 tests; worth revisiting if
xfail usage grows, not worth the complexity for v1.

## Open item carried into the implementation plan

None outstanding — the one live decision (trace scope) is resolved above
(web-app-triggered runs only). Everything else in this spec reflects
explicit approval from Logan in chat, 2026-09-10.
