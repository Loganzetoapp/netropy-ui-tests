# Netropy UI Test Suite — instructions for Claude Code

## What this is
Automated Playwright (Python/pytest) UI tests for the Apposite Netropy Traffic
Generator 4.0 web interface. The full test plan is in `netropy-ui-test-plan.md`
— read it before implementing a new test area. Test functions are named after
their plan area, e.g. `test_t6_subnet_25_computes_126_clients`.

## Environment
- Target box URL and credentials come from `.env` (see `.env.example`).
  Never hardcode credentials in test files. Never commit `.env`.
- The box is shared lab hardware. Other people may be using it.

## Markers — the safety rule
- `hardware_free`: pure UI tests. No traffic, no port reservation, no Reset.
  Safe to run anytime. Default choice.
- `stateful`: activates testbeds and generates real traffic. NEVER run
  `-m stateful` without the user explicitly asking. Never run stateful tests
  in parallel (no xdist). Always release ports / stop tests in teardown.
- `smoke`: subset of hardware_free, the 2-minute sanity set.
- `quarantine`: known flaky, excluded by default in pytest.ini.
- Never mark a test both stateful and hardware_free.
- Never automate "Reset All" on the dashboard.

## Conventions
- Selectors: role-based, scoped to a row or card first, e.g.
  `page.get_by_role("row", name="Port 4").get_by_role("switch")`.
  No brittle CSS chains. If a selector needs a data-testid that doesn't
  exist, note it in the PR description instead of working around it.
- Assertions: use playwright `expect()` web-first assertions, not sleeps.
  Never assert on the live UTC clock, uptime, or elapsed-time badges.
- One spec file per feature area. Fixtures go in conftest.py.
- Auth is handled by the session-scoped fixture — tests receive an
  already-authenticated `page`. Don't write login steps inside tests.

## Workflow
- Run tests with `pytest -m hardware_free` (add `--headed` when debugging).
- On failure: inspect the trace/screenshot in results/artifacts, fix the
  selector or the test, re-run. If the failure looks like a product bug,
  stop and report it to the user instead of changing the test to pass.
- A test must pass 3 consecutive runs before it's considered done.

## Results dashboard
Every `pytest` run writes a small summary to `results/history/<run-id>.json`
(committed — see .gitignore) and rebuilds `results/index.html` automatically
(a conftest.py hook; zero extra steps). Open `results/index.html` directly
in a browser (file://, no server) to see: latest run status, a 30-run
trend chart, per-test stability across back-to-back runs on one commit,
a flaky-test ranking across all history, the 10 slowest tests with a
trend arrow, and this run's failures with links to their screenshots.
Rebuild by hand from existing history (no test run) with `make report` or
`python scripts/build_report.py`.

**Stability run** — the deliberate way to populate the "Stability
sessions" section for a commit (rather than relying on it filling in
incidentally): run the same marker set N times back-to-back *without
changing anything in between*, so every run shares one git SHA.

```
for i in {1..5}; do pytest -m hardware_free; done
```

Each iteration appends its own `results/history/*.json` and rebuilds the
report, so `results/index.html` accumulates all 5 runs live. Open it
afterward and check the Stability section for that SHA: any test with
a red **FLAKY** badge passed on some of the 5 runs and failed on
others — that's the signal to chase, not a single failing run in
isolation. A steady 100% column with no flaky badges across all 5 is
what "done" actually looks like for a test, per the 3-consecutive-runs
rule above (5 is just extra margin).

Never do this with `-m stateful` without the user explicitly asking —
same rule as any other stateful run, and doubly so since this multiplies
however many testbed activate/traffic cycles one run already costs.
