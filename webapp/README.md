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
