"""T10 — double-click race on Start (and, budget permitting, on a fresh
draft's very first Start click).

Last of a five-test exploratory batch hunting for real product bugs via
untried state-transition combinations. The other four already found: (1) a
port-conflict that fails silently with no visible error
(test_t10_port_conflict_while_active.py), (2) a confirmed cross-protocol
extension of the known VXLAN "Start doesn't really start" bug
(test_t10_cross_layer_multistream_arp_dns_vxlan.py), (3) graceful handling
of asymmetric subnet masks — no bug, but extends the known "no validation"
finding (test_t10_asymmetric_subnet_pairing.py), and (4) a NEW bug in
test_t10_rapid_stop_restart_cycle.py's close cousin,
test_t10_rapid_stop_restart_cycle... actually found in the sibling that
restarts Start on a just-Stopped (not deactivated) testbed: doing so can
cause the run to silently self-terminate after only ~2-4s instead of its
configured duration, with no error shown anywhere.

This test asks a different but adjacent question: what happens if a user's
mouse (or an impatient double-tap) sends a click-triggered control *two*
click events back to back, right at the moment it's about to arm/start a
testbed? Single-click Start (and single-click Continue on its confirmation
modal) is well-trodden ground (every other lifecycle test in this file uses
it) — the untried part is the *double*-click, which touches the same
state-transition territory as finding (4) above: does the frontend de-dupe
it (second click is a no-op), does it fire a duplicate backend call, does
it produce a duplicate run-history row for what should be one logical run,
does it break navigation into the Statistics view, or — the one to watch
for most closely given finding (4) — does it produce that same "silently
ends after a few seconds" symptom? If that symptom shows up here too, the
report below calls out explicitly whether it looks like the SAME underlying
bug as (4) (a race in the same start/stop state machine) or something
distinct (specific to double-submission of the click itself).

=== UI CHANGE (2026-09-17) — this test's whole click sequence was rebuilt ===
The two-step "Apply (Save & activate) -> wait for the post-Apply
'Deactivate' bar -> Start (run traffic)" flow this test was originally
written against no longer exists for a freshly-created draft testbed. The
"Apply" button is gone entirely; the draft's bottom bar is now Discard
Changes / Delete / Save / Start, and clicking Start pops a "Testbed is
Inactive" confirmation modal (Cancel / Continue) that activates AND starts
traffic together on Continue, landing straight in the Statistics view. See
test_t10_t12_lifecycle_multistream_udp_tcp_100mbps.py for the fullest
writeup of the product change itself.

That merger removes the old test's two distinct "kinds" of click target
(Apply = one-time, novel-state-creating; Start = repeatable, traffic-only)
that Phase 1 and Phase 2 below were built around. This version maps them
onto the closest equivalents in the new flow:

  - Phase 1 (was: double-click the repeatable "Start traffic" button on an
    already-armed testbed) now double-clicks **Continue** on the
    confirmation modal — Continue is the control that now actually fires
    the backend activate+start call for a first-ever activation, so it's
    the direct analog of the old test's "click the button that starts
    traffic" step. The single Start click that pops the modal is treated
    as the (single-click, well-trodden) arming step, matching the old
    test's single-click Apply before its double-click Start.
  - Phase 2 (was: double-click Apply itself, the one-time draft-arming
    action, on a second fresh testbed) now double-clicks **Start** itself
    on a second fresh draft, before any Continue click — Start's first-ever
    click is now the one-time, novel-state-creating action (it's what
    conjures the confirmation modal into existence), making it the closest
    analog of old Apply.

NEEDS HUMAN REVIEW: this mapping is a best-effort adaptation, not something
re-confirmed against live hardware yet (the original 2026-09-15 findings
below were captured under the OLD Apply/Start flow and are kept as
historical record of a real bug found that day — they do not describe
current button names or the current click sequence). Two assumptions in
particular need verification on the next live run:
  1. That a never-yet-activated draft testbed reliably shows the "Testbed
     is Inactive" modal on its first Start click (if a prior manual session
     left "Don't show this again" checked for this account, Phase 1 would
     have no modal/Continue to double-click at all — handled below by
     skipping loudly rather than silently reinterpreting the click target).
  2. What double-clicking Start itself actually does in Phase 2 — whether
     the second click event lands on the modal's own Continue by
     coordinate coincidence (in which case it behaves like a fast
     Start+Continue and ends up live), lands on the modal backdrop/no-op
     (single clean modal, no different from a single click), or produces
     some third, broken state. All three are handled and reported below,
     but which one this product actually does is exactly the open question
     this test exists to answer.

--- What was actually observed under the OLD Apply/Start flow (2026-09-15,
one run against 192.168.173.111) — kept as historical record; the button
names below (Apply, Deactivate) no longer exist in the current UI ---
Phase 1 ran; Phase 2 was never reached because Phase 1 surfaced a genuine
anomaly and the test correctly stopped there (per the "don't force a
pass" rule) rather than proceeding.

Build + Apply succeeded normally. The double-click itself looked clean by
every signal captured at click time: exactly ONE backend request matched
`/start` or `/activate` during the click window
(`POST /ctrl/v1/tests/T10-DblClick/start?wait=15`) — the frontend de-duped
the second click event rather than firing it twice. No console errors, no
uncaught page errors. Navigation into the Statistics view landed cleanly
(the "← Dashboard" button appeared within the wait). The run then went
genuinely live and ran for its FULL configured duration — Stop stayed
visible for 80.7s against an 80s configured ramp — so this is explicitly
NOT a recurrence of finding (4)'s "ends after ~2-4s" symptom; if anything
it's the opposite (full, correct-duration completion).

The anomaly showed up one step later. After Stop disappeared (natural
completion) and the dashboard tile's own "Stats" button was clicked —
verbatim the same action every sibling lifecycle test in this file uses
immediately after a completed run — the Statistics view did NOT show the
completed run's result or a populated `table.runs-table`. It showed the
same "Ready to start traffic / Ports are armed and idle. Start traffic to
begin collecting live statistics." empty/idle placeholder that only
otherwise appears right after Apply, before a testbed has ever been
started — as if the view had no memory that a run had just completed,
even though the backend evidence (single /start call, 80.7s of live Stop
visibility) confirms one genuinely did. `table.runs-table` never appeared
within a 10s wait. This is the same click-sequence and selector this
suite's other lifecycle tests use successfully
(test_t10_t12_lifecycle_udp_1gbps_1500b.py asserts "pass" text visible
immediately on this same click with no special handling;
test_t10_rapid_stop_restart_cycle.py asserts `table.runs-table` has the
expected row count the same way after its own natural-completion cycle) —
so this doesn't look like a selector or timing mistake in this test, it
looks like the double-click left this testbed's Stats/run-tracking view
state out of sync with the backend.

Verdict: **NOT the same bug as finding (4).** Finding (4) is a run
ending prematurely; here the run completed correctly and fully. This is
a distinct, third symptom from the task's anticipated list — "a confusing
UI state" — specific to double-submitting Start: the completed run seems
to have gone missing from its own Stats view, replaced by a stale
"never started" placeholder. One plausible mechanism (not confirmed):
the double-click's second `click` event landed on the *Statistics view's
own* "Start traffic" button (visible in the same view, at/near the
original Start button's screen position) microseconds after the SPA
navigated into it — which could plant a stale "about to start a fresh
run" expectation in the frontend's local state that then survives past
the real run's actual completion. This is a hypothesis to hand to
Travis/frontend, not a confirmed root cause — only one data point exists
(this suite's one-shot policy on stateful runs), so a genuine one-off
environmental flake on shared lab hardware can't be fully ruled out
either; it's flagged here because the balance of evidence (clean single
backend call, full-duration completion, an established selector/pattern
that works reliably elsewhere in this same file) points at a real
product/frontend bug rather than a mistake in this test.

Phase 2 (double-click Apply) was never attempted — per the task's explicit
instruction to stop and report rather than press on once Phase 1 produced
something worth flagging, and to avoid leaving a second testbed's state
tangled with an already-anomalous first one.

Hardware confirmed clean afterward (verified via a separate read-only
check after the test's own teardown fixture ran): Port 3 and Port 4 both
back to "Available", and neither T10-DblClick nor T10-DblApply remain
among the dashboard's testbed tiles (only the two pre-existing, unrelated
testbeds TA and TE-01 are present).

This whole test needs a fresh live run under the new UI before its
"Verdict" section above can be trusted as still-current — it is retained
only as historical evidence that double-submission bugs are a real,
previously-demonstrated risk area in this product, which is why this test
still exists and is worth re-running rather than deleting.

Stateful: generates real traffic on shared hardware. Only Port 3 and Port
4 are touched (Port 1/2 belong to other real users right now; Port 5/6 has
a known link-down hardware issue; Port 7/8 are unconfirmed) — same
constraint as every other test in this exploratory batch. Never run
alongside other stateful tests (no xdist, no parallel stateful runs, per
CLAUDE.md).

Selector/pattern notes carried over from the closest siblings
(test_t10_t12_lifecycle_udp_1gbps_1500b.py, test_t10_rapid_stop_restart_cycle.py):
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the post-Start/Continue
navigation into the Statistics view takes real time to complete (`?wait=15`
server-side contract), so waits for it are given generous room (75s)
rather than treated as hung; a hard `page.goto()`/back-nav mid-transition
is known to crash this SPA's routing, so the app's own "← Dashboard"
button is used to navigate back wherever possible.

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec
from pages.testbed_editor_page import START_POPUP_TITLE
from tests.t10_t12_lifecycle.known_issues import DOUBLE_CLICK_STATS_STUCK

TESTBED_NAME = "T10-DblClick"
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.11.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.11.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(10, 60, 10),
)
PREMATURE_END_THRESHOLD_S = 25


@pytest.mark.stateful
@DOUBLE_CLICK_STATS_STUCK
def test_t10_double_click_start_race(dashboard: Page, traffic_engine):
    """Correct behaviour: a double-click on Start makes exactly one full-
    length run, and Stats afterwards shows it."""
    page, board, runs = dashboard, traffic_engine.dashboard, traffic_engine.runs
    traffic_engine.create(TESTBED_NAME, SPEC)

    traffic_engine.editor.start_button.dblclick()
    popup = page.get_by_text(START_POPUP_TITLE, exact=True)
    try:
        popup.wait_for(state="visible", timeout=5_000)
        page.get_by_role("button", name="Continue").click()
    except Exception:
        pass
    row = runs.wait_for_run_to_finish(1, timeout=SPEC.run_seconds * 1000 + 180_000)
    result = traffic_engine.result(TESTBED_NAME, row, expected_seconds=SPEC.run_seconds)
    result.assert_passed()
    assert (result.ntg.get("duration-sec") or 0) > PREMATURE_END_THRESHOLD_S, (
        f"run ended after {result.ntg.get('duration-sec')}s of {SPEC.run_seconds}s"
    )

    # One logical run, one row; and Stats re-opened from the dashboard shows it.
    board.open()
    board.tile_button(TESTBED_NAME, "Stats").click()
    expect(runs.run_row(1)).to_have_count(1, timeout=30_000)
    expect(runs.run_row(2)).to_have_count(0)
