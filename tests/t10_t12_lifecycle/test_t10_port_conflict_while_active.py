"""T10 — port conflict while a testbed is actively using it.

Exploratory test, not a happy-path regression. The plan's T10 section
covers *disjoint* concurrent testbeds (see test_t10_two_testbeds_simultaneous.py
— Testbed A on Port 1+2, Testbed B on Port 3+4, verified to genuinely
overlap). It never covers the inverse: what happens if a *second* testbed
tries to claim ports a *first*, currently-live testbed is already using.
That's the gap this test hunts in.

Port note (2026-09-15): only Port 3 + Port 4 are confirmed safe to use
right now (a late constraint from Logan, after Port 1/2 were originally
planned for this test — see git history of this file). So, unlike most
lifecycle siblings, there's no separate disjoint "control" pair available
here — and none is actually needed: the conflict only requires one
testbed's ports to be attempted twice. Testbed A gets Port 3 + Port 4,
real and live; Testbed B then attempts to claim that *exact same pair*
while A is still running. A pre/post snapshot of Port 3's own dashboard
row (captured before anything reserves it, then again once A holds it)
stands in for the cross-port "known available" comparison other tests in
this file would normally use.

Scenario: build and Start Testbed A on Port 3 + Port 4 — real traffic,
actually running. While A is live, open a second testbed's (Testbed B)
wizard and, on its Ports step, attempt to also enable Port 3 and Port 4 —
exactly the pair A is actively using.

Expected/correct behavior (asserted): the product should not let Testbed
B silently claim ports a live testbed is already using. That could
reasonably show up as — the ports' rows/toggles in B's Ports step
reading as unavailable and refusing to toggle on; the dashboard row
showing something other than "Available" while A holds them; or, at
worst, an explicit, visible block/error if the wizard lets the toggle
proceed but Start/Continue is where the conflict is actually caught. What
would NOT be acceptable: B's toggles turning on with no signal at all,
Start/Continue silently succeeding with both testbeds now claiming the
same ports, or Testbed A's live run breaking/disappearing as a side
effect of B's attempt.

This mirrors the two-testbed sibling's builder helpers (_reserve_ports /
_release_ports / _delete_testbed_if_present / _build_and_start_testbed)
rather than reinventing them — see that file's docstring for the
CSS-position selector caveats shared by every wizard step in this suite.
(That sibling file's own helper is still named `_build_and_apply_testbed`
with a separate `_start_testbed` step, predating the 2026-09-17 UI change
described below — this file's local helper has been renamed/merged to
match the new single-action flow; see `_build_and_start_testbed`'s own
docstring for why.)

Stateful: generates real traffic on shared hardware. Never run alongside
other T10/T12 lifecycle tests (no xdist, no parallel stateful runs, per
CLAUDE.md).

=== UI CHANGE (2026-09-17) ===
The "What was actually observed" section right below predates a product
UI change: the draft testbed's "Apply" (save & activate) button no longer
exists, and its "Deactivate" bar no longer appears as an intermediate
armed-but-not-started state. A draft's bottom bar now reads Discard
Changes / Delete / Save / Start, and Start pops a "Testbed is Inactive"
confirmation modal (Continue) that activates AND starts traffic together,
landing straight in the Statistics view — see
test_t10_t12_lifecycle_multistream_udp_tcp_100mbps.py for the full
writeup. The code below has been updated to use Start+Continue and to
check for the Statistics heading instead of a "Deactivate" bar, but the
specific finding recorded below (Testbed B's activation attempt failing
silently, with no visible error) has NOT been re-confirmed against
hardware since that change — NEEDS HUMAN REVIEW on the next live run to
check whether Testbed B's Start+Continue attempt still fails the same
silent way, or surfaces differently now (e.g. an error after Continue,
or the modal itself refusing to open).

--- What was actually observed under the OLD Apply/Deactivate flow
(2026-09-15, one run against 192.168.173.111) — kept as historical record;
"Apply" and "Deactivate" below no longer exist in the current UI ---
Testbed A (UDP, Port 3+4, 1 Gbps, 10/180/10s ramp) built, Applied, and
Started cleanly — confirmed live (Stop visible on its tile) before any
conflict probing began.

Dashboard-level signal (non-destructive read): Port 3's row went from
"...Available...Reserve" (captured before this test reserved anything)
to "...Reserved / test (you) / T10-Conflict-A / Release" once A held it
— a clear, correctly-attributed ownership change.

Wizard-level signal (Testbed B's own Ports step): Port 3's row read
"⚠ in use by testbed \"T10-Conflict-A\"" — and so did Port 4's. So the
product DOES surface, by name, exactly which testbed already holds a
port, right in the Ports-step table of a second testbed being built.

However — the toggle switches for both Port 3 and Port 4 were NOT
disabled. Clicking them turned them on exactly as a free port's toggle
would (their "line rate" fields became visible and fillable), with no
confirm dialog, no blocking tooltip, nothing to stop selection beyond the
informational warning text already sitting right there in the same row.
Filling in both ports' config and finishing the rest of Testbed B's
wizard (network config, one UDP stream, traffic/load profile) and
clicking Apply: the call did NOT silently succeed — Testbed B never
reached an activated state (no "Deactivate" bar appeared within 30s), and
Testbed A was reconfirmed live and unaffected afterward (its Stop button
was visible again via a proper `expect()` wait by the end of the test;
see selector note below on why an intermediate plain `.is_visible()`
snapshot briefly, spuriously, read False).

Verdict: **not a silent-acceptance bug.** The product ultimately blocks
the conflicting activation and never corrupts Testbed A's running state
— the invariant this test actually guards on (no silent conflict, no
corrupted live testbed) held, so the test passes. But it's a genuine,
worth-flagging UX gap: the Ports step already has the exact information
needed ("⚠ in use by testbed \"T10-Conflict-A\"") rendered right on the
row, but doesn't use it to disable the toggle or block selection before
Apply — a user only finds out the port is unavailable after configuring
an entire second testbed end-to-end and clicking Apply at the very end,
with no visible-in-this-run indication of *why* it didn't activate (no
toast/error text was seen in this run's UI at the point Apply silently
failed to transition — only the absence of the expected "Deactivate"
button gave it away). That absence-of-explicit-error is itself a repeat
of the same UX gap already logged in netropy-ui-findings.md ("The
frontend shows nothing when activation fails") — this test reproduces
that same silence for a *different* underlying cause (port conflict, not
the 15-char name limit). Reported to Logan per the "report UI issues"
convention rather than worked around; not asserted as a hard failure
here since the task's actual bar for a bug (silent *acceptance* of the
conflict, or corruption of A) was not met.

Selector note (this test's own imprecision, not a product bug): right
after Testbed B's failed Apply, a diagnostic-only `tile_a.get_by_role(
"button", name="Stop").is_visible()` (a single snapshot with no wait,
used only for a print statement) read False immediately after navigating
back to the dashboard — almost certainly because the dashboard's tile
list briefly re-renders on that navigation and the plain read raced it.
The test's actual final assertion re-checks the same locator through a
proper `expect(...).to_be_visible()` (auto-retrying up to the default 10s),
which passed — confirming A was genuinely still live throughout. Kept the
plain read in for its diagnostic print value but it should not be read as
evidence of real instability; same "don't trust an unwaited snapshot"
lesson as the UDP lifecycle sibling's own "BUG FOUND" note about racing
Start.

Hardware confirmed clean afterward: Port 3 and Port 4 back to
"Available", both testbeds deleted, no tiles left on the dashboard. Port
1 and Port 2 were never touched by this test at all — they were already
"Reserved" by pre-existing testbeds `ta-c1`/`ta-s2` (owner `admin`)
before this test ran, and are unchanged.

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec
from pages.testbed_editor_page import START_POPUP_TITLE
from tests.t10_t12_lifecycle.known_issues import PORT_CONFLICT_SILENT

TESTBED_A_NAME = "T10-Conflict-A"
TESTBED_B_NAME = "T10-Conflict-B"
SPEC_A = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.7.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.7.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=1000, ramp=(5, 90, 5),
)
SPEC_B = TestbedSpec(ports={3: PortSpec(rate=1), 4: PortSpec(rate=1)},
                     streams=[StreamSpec("UDP")], duration_s=20)


@pytest.mark.stateful
@PORT_CONFLICT_SILENT
def test_t10_port_conflict_while_active(dashboard: Page, traffic_engine):
    """Correct behaviour: while A is live on Ports 3/4, B's editor shows
    them in use, B's Start is refused with a visible message, and A keeps
    running."""
    page, board, ed = dashboard, traffic_engine.dashboard, traffic_engine.editor
    traffic_engine.create(TESTBED_A_NAME, SPEC_A)
    traffic_engine.start(TESTBED_A_NAME)
    board.open()
    board.keeps_running(TESTBED_A_NAME, 5)

    traffic_engine.create(TESTBED_B_NAME, SPEC_B)
    for port in (3, 4):
        expect(ed.port_row(port)).to_contain_text("in use", ignore_case=True)

    ed.start_button.click()
    popup = page.get_by_text(START_POPUP_TITLE, exact=True)
    try:
        popup.wait_for(state="visible", timeout=5_000)
        page.get_by_role("button", name="Continue").click()
    except Exception:
        pass
    # A visible refusal, not silence.
    expect(page.locator(".toast")).to_contain_text(
        re.compile(r"in use|conflict|reserved|busy", re.I), timeout=20_000
    )
    board.open()
    expect(board.is_running(TESTBED_B_NAME)).to_have_count(0)
    board.keeps_running(TESTBED_A_NAME, 20)
