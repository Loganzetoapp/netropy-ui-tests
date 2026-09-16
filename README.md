# Netropy UI Tests

Playwright (Python) UI test suite for the Netropy Traffic Generator 4.0.

## Setup
    make setup

Then fill in real values in `.env` (created for you from `.env.example`)
and run `pytest -m smoke --headed` to confirm it works.

`make setup` just automates: creating a `.venv`, `pip install -r
requirements.txt`, `playwright install chromium` (on Linux, also the
OS-level libraries headless Chromium needs via `apt` — may prompt for
your sudo password), and copying `.env.example` to `.env` if you don't
have one yet — safe to re-run any time (e.g. after `pip install`-ing a
new dependency).

## Running
- pytest -m hardware_free      # safe anytime
- pytest -m smoke              # quick sanity
- pytest -m stateful           # generates traffic — coordinate first
- add --headed to watch

See netropy-ui-test-plan.md for the full plan and CLAUDE.md for conventions.

## Prefer a browser to a terminal?
`make run-dashboard` runs a local, no-terminal test dashboard — browse
tests, click Run, watch live results. See `webapp/README.md`. Runs
entirely on your own machine against your own `.env`, same rules as above.

## Results dashboard
Every `pytest` run updates `results/index.html` automatically — open it in
a browser (no server needed) for pass/fail history, flaky-test tracking,
and slowest tests. Rebuild by hand anytime with `make report`.

Quick ways to open it:
- Terminal: `open results/index.html`
- Cursor/VS Code: Command Palette → "Simple Browser: Show" → paste the
  URL from `results/report-url.txt` (kept up to date, one line, ready to
  copy — not committed, it's a local convenience file, path is
  machine-specific)
