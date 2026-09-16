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
- **Findings** tab: `netropy-ui-findings.md`, rendered in the browser —
  no need to open the file in an editor to see what's been found.
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

### Running it unattended (e.g. a dedicated Ubuntu box)

`make run-dashboard` is a foreground process — fine for sharing with one
other person while you're at your desk, not something to rely on for a
machine other people reach remotely whenever they want. `deploy/netropy-
dashboard.service` is a systemd unit that runs it as a real background
service instead: starts on boot, restarts automatically if it ever
crashes, logs go to `journalctl -u netropy-dashboard` (rotated
automatically). See the comments at the top of that file for the
install steps — it's a few `sudo systemctl` commands after one manual
edit (the deploy user and repo path for that machine).

## Failure review

Every dashboard-triggered test failure gets its evidence captured
automatically — a summary extracted from its Playwright trace (action
sequence, JS/console errors, any non-2xx network responses) plus the
failure screenshot. What happens with that evidence depends on whether
`ANTHROPIC_API_KEY` is set in `.env`:

**Unset (default) — free pending-review queue.** The evidence is logged
straight into `netropy-ui-findings.md`, under "Dashboard failures —
pending review" — timestamped, with links to the screenshot/trace. No
API key, no cost, no extra setup, always on. These entries are raw
evidence, not yet reviewed — to actually review one, ask Claude in a
Claude Code session in this repo: it reads the trace/screenshot the same
way it would if you handed it the file directly, then either promotes a
real one into "Confirmed product issues" above (with what makes it
confirmed) or notes why it isn't (test/selector issue, inconclusive,
etc.), and marks the entry reviewed.

**Set — automatic review, no session required.** The same evidence is
sent directly to Claude (Haiku 4.5 — a few cents a day at typical failure
volume), and the resulting evidence-grounded finding is appended straight
to `netropy-ui-findings.md` under "Dashboard failure reviews (automatic)"
— nobody has to be around interactively reviewing a queue for findings to
show up. This is what makes an unattended, remote-hosted dashboard
usable without a human/Claude session babysitting it. These are still
single-run automated reads, kept in their own section rather than mixed
into the manually-reproduced "Confirmed product issues" section — worth
a glance before fully trusting one, same as any single-run read. If the
API call itself fails (bad key, network error, rate limit), that
iteration falls back to the free pending-review queue automatically
rather than losing the evidence.

The **Findings** tab in the dashboard is the easiest way to see either
mode's output without opening the file in an editor.

## Design

See `DESIGN.md` for the color/type/component tokens this UI is built
from (matched to the real Netropy Traffic Generator UI, not invented).

## Backend tests

    pytest --confcutdir=webapp webapp/tests/ -v

(`--confcutdir=webapp` keeps this from picking up the repo-root
`conftest.py`, which is for the real Playwright suite and would
otherwise try to write a spurious `results/history` entry for these
fast unit tests too.)
