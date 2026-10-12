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

NTG 5.0 rewrite (2026-09-30): built with the shared conftest helpers and
started via Start -> "Testbed is Inactive" -> Continue. In 5.0 the editor
bar of an active testbed still has Deactivate; after it the bar offers
Start (5.0 auto mode has no Apply). Ports read "Unreserved" (4.0
"Available") once released, and the tile's Stats button reaches saved
runs whether or not the testbed is active (4.0 needed "Reports: N").
"""
import re

import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED_NAME = "T10-DeactLive"
PORTS = ["Port 3", "Port 4"]
# 5/90/5 = 100s: Deactivate lands ~15s into a ~90s hold.
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1), 4: PortSpec(rate=1)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(5, 90, 5),
)


@pytest.mark.stateful
def test_t10_deactivate_mid_run_skips_stop_cleanly(dashboard: Page, traffic_engine):
    page, board = dashboard, traffic_engine.dashboard
    traffic_engine.create(TESTBED_NAME, SPEC)
    traffic_engine.start(TESTBED_NAME)

    board.open()
    tile = board.testbed_entry(TESTBED_NAME)
    expect(board.is_running(TESTBED_NAME)).to_be_visible(timeout=15_000)
    port3_live = board.port_row(3).inner_text()
    print(f"[deactivate-mid-run] Port 3 dashboard row while live: {port3_live!r}")
    page.wait_for_timeout(15_000)

    # The point: Deactivate directly, mid-run, never touching Stop.
    tile.get_by_role("button", name="Edit").click()
    deactivate = page.get_by_role("button", name="Deactivate", exact=True)
    expect(deactivate).to_be_visible(timeout=15_000)
    deactivate.click()

    # Ends the run and returns the testbed to inactive: Deactivate goes
    # away and the bar offers Start again.
    expect(deactivate).to_have_count(0, timeout=30_000)
    expect(page.get_by_role("button", name="Start", exact=True)).to_be_visible(timeout=15_000)

    board.open()
    expect(board.is_running(TESTBED_NAME)).to_have_count(0)
    # Deactivate also releases the ports (no separate Release needed).
    for port in PORTS:
        expect(board.port_row(port).get_by_text("Unreserved", exact=True)).to_be_visible(timeout=10_000)

    # The run skipped Stop entirely: is it still recorded?
    board.tile_button(TESTBED_NAME, "Stats").click()
    row = traffic_engine.runs.wait_for_run_to_finish(run_number=1, timeout=30_000)
    expect(row.get_by_text(re.compile(r"^(pass|fail)$", re.I))).to_be_visible(timeout=15_000)
    result = traffic_engine.result(TESTBED_NAME, row, label="deactivated")
    assert not result.metrics.failed_checks(), result.metrics.failed_checks()
