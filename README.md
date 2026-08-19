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
