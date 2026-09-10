# Netropy UI Tests

Playwright (Python) UI test suite for the Netropy Traffic Generator 4.0.

## Setup
1. python3 -m venv .venv && source .venv/bin/activate
2. pip install -r requirements.txt
3. playwright install chromium
4. cp .env.example .env  # fill in credentials
5. pytest -m smoke --headed

## Running
- pytest -m hardware_free      # safe anytime
- pytest -m smoke              # quick sanity
- pytest -m stateful           # generates traffic — coordinate first
- add --headed to watch

See netropy-ui-test-plan.md for the full plan and CLAUDE.md for conventions.

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
