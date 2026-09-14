# Netropy Test Dashboard

A local, browser-based dashboard for browsing and running this repo's
Playwright tests — no terminal, no pytest/Playwright knowledge needed.

## Run it

First time on this machine? `make setup` (see the root `README.md`) —
creates a `.venv`, installs dependencies, downloads the Chromium browser,
and creates `.env` for you to fill in with real lab-box credentials.

Then:

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

## Sharing the dashboard

By default this only listens on your own machine (`127.0.0.1`) with no
login — nothing to configure, same as always.

To let other people on the network use it too (one person runs it, everyone
else opens it in their browser), set in `.env`:

    WEBAPP_HOST=0.0.0.0
    WEBAPP_USER=some-shared-username
    WEBAPP_PASSWORD=some-shared-password

then `make run-dashboard` again. It prints the URL to share (your machine's
LAN address). Every visitor's browser will prompt for that username/password
once and remember it.

**Both `WEBAPP_USER` and `WEBAPP_PASSWORD` are required whenever `WEBAPP_HOST`
isn't localhost — the server refuses to start otherwise.** This dashboard can
trigger real traffic on the lab hardware; opening it to the network with no
login would let anyone who can reach the machine do that. The one-test-at-a-
time rule is enforced server-side regardless of how many people are looking
at it, same as running it solo.

## Automatic failure review

Set `ANTHROPIC_API_KEY` in `.env` and every dashboard-triggered test
failure gets automatically reviewed: the failure screenshot and a summary
extracted from its Playwright trace (action sequence, JS/console errors,
any non-2xx network responses) are sent to Claude, and the resulting
evidence-grounded finding is appended to `netropy-ui-findings.md` under
"Dashboard failure reviews" — timestamped, with links back to the
screenshot/trace. These are single-run automated reads, kept in their own
section rather than mixed into the manually-reproduced "Confirmed product
issues" section above it. Leave `ANTHROPIC_API_KEY` unset to disable —
this costs a real API call per failed run.

## Design

See `DESIGN.md` for the color/type/component tokens this UI is built
from (matched to the real Netropy Traffic Generator UI, not invented).

## Backend tests

    pytest --confcutdir=webapp webapp/tests/ -v

(`--confcutdir=webapp` keeps this from picking up the repo-root
`conftest.py`, which is for the real Playwright suite and would
otherwise try to write a spurious `results/history` entry for these
fast unit tests too.)
