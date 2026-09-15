"""T10 — Deactivate mid-run: skip Stop entirely and hit Deactivate directly
while traffic is still flowing.

Every lifecycle test that interrupts a run before now goes through Stop
first: `test_t10_stop_mid_run` clicks the dashboard tile's Stop button
mid-hold and confirms the run ends and gets recorded, and
`test_t10_rapid_stop_restart_cycle` cycles Stop -> Start -> Stop on a
still-Applied testbed. Natural completion (every other UDP/TCP/ICMP/etc.
sibling) always leaves the testbed ACTIVE-but-idle, reached via Stop never
being clicked at all. Nobody has yet asked the product to collapse
"Stop, then Deactivate" — normally two separate user actions — into one:
clicking **Deactivate** directly while traffic is actively transmitting,
before Stop is ever pressed.

Unlike Stop (a button on the dashboard tile itself), Deactivate lives in
the 4-step wizard/edit view's action bar — the same bar that swaps from
Discard/Delete/Save/Apply (draft) to Delete/Deactivate/Stats/Save/Start
once Apply succeeds (see the UDP reference test's Activate/Start
commentary). To reach it mid-run this test clicks the dashboard tile's
own **Edit** button while the tile is showing Stop (i.e. while still
live) — that action/button was previously only ever exercised on a
draft, pre-Apply testbed (`test_t10_stop_mid_run`,
`test_t10_t12_lifecycle_udp_1gbps_1500b`); using it on an already-active,
currently-transmitting testbed is itself new territory this test
confirms works before ever touching Deactivate.

Uses a deliberately long hold phase (5/90/5 = 100s total) so Deactivate
lands solidly mid-run (~15s in, ~80s of hold still remaining, well clear
of both the ramp-up transient and natural completion) — same rationale
as the Stop-mid-run sibling's timing.

Ports 3 + 4, UDP, 1500-byte frames, 1 Gbps — the suite's standard
low-risk single-testbed profile, since this test's point is the
Deactivate control, not stream config. (Only Port 3/4 are confirmed safe
on this box right now — Port 1/2 reserved by something else, Port 5/6
link-down, Port 7/8 unconfirmed.)

What this test is actually hunting, genuinely open questions with no
pre-registered "correct" outcome:
  1. Does Deactivate mid-run cleanly stop traffic and release the active
     state in one action, or does it get confused skipping the Stop step
     it presumably expects to happen first?
  2. Is the run's result correctly recorded in run-history afterward (a
     real PASS/FAIL/MANUAL-STOP-style row), or does skipping Stop leave
     no result / a phantom "still running" row / something corrupted?
  3. Does the dashboard's Port Status table correctly show Port 3 and
     Port 4 back to some sane non-stuck state afterward?

CONFIRMED (reproduced identically across two separate live runs,
2026-09-15): question 3's answer is a genuine, previously-untested
behavioral difference from Stop, not a bug. Ports 3 and 4 were reserved
via the dashboard's own per-port "Reserve" button *before* this test ever
created or activated the testbed — a reservation that, in every sibling
lifecycle test, is scoped to the user/session and outlives Stop (Stop
mid-run leaves ports "Reserved"; teardown always calls the port row's own
"Release" separately). Clicking the wizard action bar's standalone
"Deactivate" directly, mid-run — never touching the port row's "Release"
button at all — nonetheless dropped the reservation outright: both ports
read "Available" (Reserve button, "—" owner) immediately afterward, not
"Reserved". So Deactivate implicitly cascades into a full release, where
Stop does not. Not a stuck/broken state (no bug in that sense — the
opposite of stuck, if anything), but a real, silent side effect worth
knowing: a user who Deactivates mid-run to reconfigure a testbed, meaning
to keep their port reservation while they edit, loses it with no
warning, and another user on this shared box could immediately grab the
port. Both live runs also confirmed the transition itself is clean and
fast (Deactivate button disappears, the draft-style Apply bar returns,
dashboard tile drops "Stop") — no crash, no hang, no stuck "Deactivate"
state. Question 2 (run-history) is NOT yet confirmed either way — see
"Known gap" below.

Known gap, disclosed rather than silently patched over: both live runs
hit a *test* bug (this file's own now-corrected assumption that ports
would stay "Reserved") at the Port Status check, which sits before the
run-history/"Reports:" check later in the test — so neither run directly
opened the Reports/Stats page to inspect the runs table. The code path
for that final check exists and mirrors the pattern already proven out
in `test_t10_stop_mid_run.py`, but it was never executed.

That said, both runs' failure snapshots (Playwright's accessibility-tree
dump, captured automatically at the point of the Port Status assertion
failure) incidentally captured the dashboard's own Testbeds card for
T10-DeactLive in full, and it's the same in both. Every *other* testbed
on the box with at least one recorded run (`TA`, `TE-01`, both with
saved runs from unrelated prior work) shows a small numbered button next
to "Linerate: ... · Streams: ..." carrying the tooltip text "View saved
runs on the Stats page" — that's the Reports/run-count control,
confirmed elsewhere in this suite (`test_t12_run_history_and_exports.py`)
as `get_by_role("button", name="Reports:", exact=False)`. That tooltip
text does not appear anywhere in T10-DeactLive's card in either dump —
its card goes straight from `Linerate: 20G · Streams: 1` to the
`Activate`/`Edit` buttons, with nothing recorded-runs-shaped in between.
The natural reading is that ending a run via Deactivate-without-Stop did
not produce a run-history entry at all — a real anomaly, not the "no
result" scenario shrugged off, if confirmed: it would mean a run's
result (and whatever traffic it generated) is silently lost rather than
recorded as some odd status. This is indirect evidence (an absent
control in a DOM dump captured for an unrelated assertion), not a direct
read of the runs table, so it's flagged here as a strong lead rather
than a fully confirmed finding — worth a deliberate follow-up (open
Reports on a Deactivate-without-Stop testbed and directly check for 0
rows) before treating it as certain.

Whatever happens, this test is not modified after the fact to force a
pass — a real product bug found here gets reported, not routed around.

Stateful: generates real traffic on shared hardware, then interrupts it
via a control path no other test in this suite has exercised.

Selector note: same caveats as every other lifecycle test in this file —
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`). The per-port line-rate
row lookup uses a start-anchored regex, matching the fix applied to the
other lifecycle tests after a "UNIT" column was added to the wizard's
Ports table.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-DeactLive"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=TESTBED_NAME)


def _delete_testbed_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        release_btn = row.get_by_role("button", name="Release")
        if release_btn.is_visible():
            release_btn.click()
            confirm = page.get_by_role("button", name="Deactivate & release")
            if confirm.is_visible():
                confirm.click()
            expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)


@pytest.fixture
def clean_testbed(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    yield
    _release_ports(dashboard)
    _delete_testbed_if_present(dashboard)


@pytest.mark.stateful
def test_t10_deactivate_mid_run_skips_stop_cleanly(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 3 and Port 4 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Create testbed ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 1 Gbps line rate ---
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill("1")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 4\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.11.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.11.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.11.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.11.2")
    _buffer(page)

    # --- Wizard step 3: Streams — UDP (default), 1500-byte frames ---
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("1500")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
    # 5/90/5 = 100s — a deliberately long hold phase so Deactivate can be
    # clicked solidly mid-run rather than racing natural completion.
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("5")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("90")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("5")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Confirm the run actually started before doing anything to it ---
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)

    # Snapshot Port 3's dashboard row while genuinely live, purely as
    # exploratory documentation of what "in use" looks like here — not
    # asserted against, since no prior test in this suite has looked at
    # this row while a run is actively transmitting (only "Reserved"
    # before activation and "Available" after release are established).
    port3_row_live_text = page.get_by_role("row", name="Port 3").inner_text()
    print(f"[deactivate-mid-run] Port 3 dashboard row while live: {port3_row_live_text!r}")

    # ~15s into the hold phase (after the 5s ramp-up) — comfortably clear
    # of both the ramp-up transient and the 100s natural-completion mark
    # (~80s away here).
    page.wait_for_timeout(15000)

    # --- The whole point of this test: reach Deactivate directly, mid-run,
    # without ever clicking Stop. Deactivate lives in the wizard/edit
    # view's action bar, not on the dashboard tile itself, so click into
    # Edit first — on an already-ACTIVE, currently-transmitting testbed,
    # which no prior test has done (Edit was previously only ever clicked
    # on a draft/inactive testbed).
    tile.get_by_role("button", name="Edit").click()
    _buffer(page)

    # Confirm this really is the live, post-Apply edit view (Deactivate
    # button present) rather than some stale/reset draft state — and that
    # Stop was never clicked to get here.
    deactivate_btn = page.get_by_role("button", name="Deactivate", exact=True)
    expect(deactivate_btn).to_be_visible(timeout=15000)
    deactivate_btn.click()

    # Unknown shape going in: does a bare Deactivate (mid-run, no prior
    # Stop) take effect immediately, or — like the port Release flow's
    # "Deactivate & release" — pop its own confirmation step first? Handle
    # either without assuming.
    _buffer(page)
    confirm_deactivate = page.get_by_role("button", name="Deactivate", exact=True)
    if confirm_deactivate.count() > 0 and confirm_deactivate.is_visible():
        confirm_deactivate.click()
        _buffer(page)

    # --- Deactivate should end the run and return the testbed to an
    # editable/inactive state: Deactivate itself disappears, and the
    # draft-style action bar (with Apply) comes back. Generous timeout —
    # this is a real backend state transition, same caveat as Apply's own
    # documented slowness.
    expect(page.get_by_role("button", name="Deactivate")).to_have_count(0, timeout=30000)
    expect(page.get_by_role("button", name="Apply", exact=True)).to_be_visible(timeout=15000)

    # --- Back to the dashboard: tile should no longer show Stop, and
    # ports should land in some sane non-stuck state. CONFIRMED (two
    # identical live runs, 2026-09-15): despite this test never touching
    # the port row's own "Release" button — only the wizard's standalone
    # Deactivate — both ports come back "Available", not "Reserved".
    # Deactivate cascades into a full release here, unlike Stop (which
    # leaves reservations intact; see every sibling lifecycle test's
    # teardown, which always Releases separately after Stop). Documented
    # in this file's docstring as a real, silent side effect worth
    # knowing about — not a stuck/broken state, the opposite of one.
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0)

    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)

    # --- Run history: was this run correctly recorded despite skipping
    # Stop entirely? Once fully deactivated, "Reports: N" becomes the way
    # in (per the existing "Reports: N only appears once deactivated"
    # finding) — use that rather than "Stats", which is what active
    # testbeds expose instead.
    reports_btn = tile.get_by_role("button", name="Reports:", exact=False)
    expect(reports_btn).to_be_visible(timeout=10000)
    reports_btn.click()
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible(timeout=10000)
    cells = run_row.locator("td")
    expect(cells.nth(1)).not_to_have_text("")  # Started At
    expect(cells.nth(2)).not_to_have_text("")  # Duration
    result_text = cells.last.inner_text()
    assert result_text.strip(), (
        "expected the Result cell to show some recorded outcome for a run "
        "ended via Deactivate mid-run (no prior Stop) — got an empty cell, "
        "which would mean the run's result was lost by skipping Stop"
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
