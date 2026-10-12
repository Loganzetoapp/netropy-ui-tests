"""T10 — Edit a testbed's configuration while it is LIVE and actively
transmitting.

Every lifecycle test that opens the "Edit" wizard view has, until now, done
so either on a draft (pre-Apply) testbed, or — in
`test_t10_deactivate_mid_run.py` — on an active testbed purely to reach the
Deactivate control, without ever touching a config field once inside. Nobody
has tried the thing this test tries: reserve Port 3/4, Apply + Start a real
UDP run with a deliberately long hold (5/90/5 = 100s) so there's room to
act, confirm traffic is genuinely flowing (non-zero Per-Port Aggregate
Tx/Rx), then click back into that *same live testbed's* Edit view, navigate
to the Streams step, and try to change the frame-size field while Stop is
still showing on the dashboard tile.

Genuinely open going in, no pre-registered "correct" answer:
  1. Does the product block editing outright while active (field disabled/
     read-only, or a visible "can't edit while running" message)?
  2. Does it let you type but reject Save/Apply with an error?
  3. Does it silently accept the edit? And if so — does it only apply to
     the *next* run (legitimate, non-bug outcome), or does it visibly
     touch the *current* live run (Tx/Rx or frame size actually changing
     mid-run), corrupt the eventual recorded result, or leave the edit
     view and the live view disagreeing with each other (a confusing dual
     state)? Any of those last three would be a real product bug.

Per the task's explicit instruction: this test is not modified after the
fact to force a pass. A real bug found here gets reported as found, not
routed around.

--- CONFIRMED (2026-09-15, two live runs against 192.168.173.111) — a real
product bug, outcome (3)'s worst case ---

Answer to question 1: NO, the product does not block editing while active.
The Streams step's frame-size field was fully editable while the testbed
was live and transmitting — `disabled=False`, `readonly=False`, typed
input accepted immediately, no warning banner, no confirmation dialog.

Answer to question 2/3: Save was clicked (the active-testbed action bar
shows Save, not Apply, matching the bar composition already documented in
`test_t10_deactivate_mid_run.py`) and it succeeded silently — no error
text anywhere on the page afterward, and the new frame size (800, edited
from 1500) was confirmed to persist server-side on a fresh navigation back
into Edit after the run ended.

But it did **not** just queue for the next run — it visibly disrupted the
CURRENT run, and lost that run's result:

  - The dashboard tile's Stop button was already gone within seconds of
    clicking Save (`Stop visible=False`) — far short of the configured 90s
    hold, and well before the ~15s-into-hold point where the edit was
    attempted plus any plausible completion time.
  - The Per-Port Aggregate Statistics row for Port 3, read again right
    after: packet counters that had read 473/473 (Tx/Rx) just before the
    edit had dropped to **1/1** — not merely "lower," but the shape of a
    counter that just started from scratch — while a byte-rate-looking
    column jumped up (38.8K -> 82.0K bytes, 68.3K -> 785.3K rate-ish
    figure). That pattern — Stop disappearing almost immediately, packet
    count reset to ~1 — matches, and looks like the same underlying
    state-machine issue as, the already-documented "Restarting Start after
    Stop can silently end a run in a few seconds" bug
    (`test_t10_rapid_stop_restart_cycle.py`): Save appears to implicitly
    stop-and-restart the live run under the hood, and the restarted run
    then self-terminates after only a couple of seconds instead of running
    its configured duration — except here nobody clicked Stop or Start at
    all; a plain config edit + Save did it by itself, silently, mid-run.
  - The eventual run-history row for this testbed has real, non-empty
    "Started At" and "Duration" cells — so a run genuinely happened and
    was timed — but its **Result cell is empty**, confirmed after a
    deliberate 20s poll specifically added to rule out the population-race
    the UDP reference test's own PASS check already guards against (so
    this isn't "hadn't finished computing yet"). The run's outcome was not
    merely delayed, it was lost.

Reproduced twice: an initial run hit the empty-Result assertion without
that 20s poll (a possible race, undetermined); this test was then fixed to
poll for up to 20s before judging the cell empty (matching this suite's
own established pattern for the same kind of race), and the second,
fully-instrumented run reproduced the same empty Result plus all of the
above — Stop disappearing early, the packet-counter reset, the field
accepting the edit with zero warning, and the change persisting
server-side. The fix accounted for a plausible test-side race; the bug did
not go away, so this is being reported as a real product issue, not
chased further with more live runs.

Net effect for a real user: editing ANY config field (tried here: Stream
frame size) on a testbed that's actively running traffic, and clicking
Save, is accepted with no warning that doing so will disrupt the run in
progress — it silently interrupts/restarts the live run, that restarted
run dies almost immediately, and the run's result is lost from history
rather than recorded as some explicit "aborted"/"edited-mid-run" status.
This is exactly the "silently accepts and corrupts the run's eventual
result" failure mode this test was written to watch for — reported here,
not routed around per this task's explicit instruction.

Not yet determined (would need dedicated follow-up, not attempted here to
avoid burning further live runs on this one finding): whether the SAME
underlying restart-and-die state-machine bug already suspected in
`test_t10_rapid_stop_restart_cycle.py` is the actual root cause here too
(this test's evidence is consistent with that, not proof of it), and
whether editing a *different* field (e.g. Traffic/Load Profile's line
rate, which the task also suggested) reproduces identically or differs.

Ports 3 + 4 only (Port 1/2 belong to someone else on this shared box right
now, Port 5/6 has a known link-down hardware issue, Port 7/8 are
unconfirmed) — same constraint as the rest of this exploratory batch.

Stateful: generates real traffic on shared hardware, then probes a control
path (editing a live testbed) no other test in this suite has exercised.
Never run alongside other stateful tests (no xdist, no parallel stateful
runs, per CLAUDE.md).

Selector notes carried over from every sibling in this file's family:
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the per-port line-rate
row lookup uses a start-anchored regex to survive the "UNIT" column added
to the wizard's Ports table.

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest
from playwright.sync_api import Page

from pages import PortSpec, StreamSpec, TestbedSpec
from tests.t10_t12_lifecycle.known_issues import LIVE_RUN_INTERRUPTED

TESTBED_NAME = "T10-EditLive"
EDITED_FRAME_SIZE = 800
# 5/90/5 = 100s: room to act mid-run.
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.13.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.13.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(5, 90, 5),
)


@pytest.mark.stateful
@LIVE_RUN_INTERRUPTED
def test_t10_edit_config_while_active(dashboard: Page, traffic_engine):
    """Correct behaviour: editing a live testbed's frame size and saving
    either is refused, or applies to the next run; the live run keeps
    going to its natural end and its result is saved."""
    board, ed = traffic_engine.dashboard, traffic_engine.editor
    traffic_engine.create(TESTBED_NAME, SPEC)
    traffic_engine.start(TESTBED_NAME)
    board.open()
    board.keeps_running(TESTBED_NAME, 5)

    board.open_editor(TESTBED_NAME)
    ed.set_stream_frame_size(0, EDITED_FRAME_SIZE)
    ed.save()
    board.open()

    board.keeps_running(TESTBED_NAME, 30)
    board.tile_button(TESTBED_NAME, "Stats").click()
    row = traffic_engine.runs.wait_for_run_to_finish(1, timeout=SPEC.run_seconds * 1000 + 180_000)
    result = traffic_engine.result(TESTBED_NAME, row, expected_seconds=SPEC.run_seconds)
    result.assert_passed()
    assert abs((result.ntg.get("duration-sec") or 0) - SPEC.run_seconds) <= 5, (
        f"run lasted {result.ntg.get('duration-sec')}s of {SPEC.run_seconds}s"
    )
