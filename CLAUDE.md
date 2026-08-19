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
