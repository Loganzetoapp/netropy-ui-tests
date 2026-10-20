"""T10 — Does a mutation with NO relationship whatsoever to a live testbed
still interrupt its run?

`netropy-ui-findings.md` ("Any mutating action against a live testbed
silently interrupts its own run") already documents two confirmed triggers
for the same symptom shape (`test_t10_edit_config_while_active.py`,
`test_t10_clone_while_active.py`): editing testbed X's config and Saving,
or clicking X's own Clone icon, each independently and reproducibly kill
X's in-progress run within seconds (Stop vanishes early, a packet counter
resets to ~1, the eventual run-history Result cell comes back empty). Both
of those triggers have one thing in common that this test isolates and
removes: both actions explicitly reference the live testbed's own ID —
Edit opens X's own config, Clone reads X's own config to spawn a copy of
it. Neither test tells us whether the *specific reference to X* is what
disrupts X, or whether *any* backend write at all — even one that never
mentions X, never touches X's ports, and operates on a completely
different object — is enough. That's the actual boundary of the bug, and
it matters a lot for how Travis prioritizes it: "any write referencing
this testbed" is a narrow, specific bug; "any write anywhere disrupts
whatever happens to be live" is a systemic backend concern with a much
larger blast radius.

This test builds `T10-LiveCtrl` (UDP, Port 3+4, 5/90/5 hold — the same
long-hold pattern as its Edit/Clone siblings, for room to act mid-run),
confirms it's genuinely transmitting (non-zero Tx/Rx), then performs a
mutation against a SECOND, entirely separate object that never references
`T10-LiveCtrl`'s ID, name, or ports in any way: create a brand-new draft
testbed (`T10-Unrelated`) and immediately delete it again — two real
backend writes (`POST` to create, `DELETE` to remove), zero ports touched
at any point (a fresh draft's Ports step starts with every row's USE
toggle off by default, confirmed directly before deleting it rather than
assumed), zero reference to `T10-LiveCtrl`.

Why this specific action over the task's other suggested alternatives:
explored `Save as a new profile…` (T9) first, since it's the most
obviously "not a testbed" mutation available — but
`tests/t9_network_profiles/test_t9_save_profile_from_wizard.py` shows it
only becomes available after toggling at least one port's USE on in the
wizard, and the resulting profile records which port position it was
built from (`P1 ⇄ P2` in that test). Even though that toggle never
reserves real hardware (the T9 test is `hardware_free` and never clicks
Reserve on the dashboard), it's still a port reference of *some* kind in
the object being saved, and the port constraint here means it would have
to be Port 3 or Port 4 specifically — the same physical ports
`T10-LiveCtrl` is running on, which would muddy "no relationship to its
ports" even if not a real hardware conflict. A create-and-delete draft
testbed with literally nothing configured (not even a port toggle
clicked) is the cleanest available option given what the live UI offers:
a real, uncontestable backend write, with zero ports touched, zero shared
identity with the live testbed.

Genuinely open going in, no pre-registered "correct" answer:
  - If `T10-LiveCtrl` keeps running undisturbed through the unrelated
    create+delete — Stop still visible well inside its 90s hold, Tx/Rx
    counters still climbing rather than reset, and it eventually completes
    with a real, non-empty run-history Result — that CONFIRMS the existing
    finding's boundary: the bug requires a write that actually references
    the specific live testbed (its config, or a read+copy of it), not just
    any backend write anywhere. A valuable negative result, not merely "no
    bug found."
  - If `T10-LiveCtrl`'s Stop vanishes early / its counters reset / its
    Result is lost — even though `T10-Unrelated` never mentions
    `T10-LiveCtrl` by name, ID, or port — that is a materially bigger,
    more alarming finding than either sibling test found: it would mean
    *any* backend write at all, anywhere, disrupts *whatever happens to be
    live* at the time, not just writes that reference that specific
    object. Per this task's explicit instruction, that outcome is reported
    in full and the test is NOT modified afterward to force a pass.

Ports 3 + 4 only (Port 1/2 belong to someone else on this shared box right
now, Port 5/6 has a known link-down hardware issue, Port 7/8 are
unconfirmed/risky) — same constraint as the rest of this exploratory
batch, and the reason `T10-Unrelated` is built with zero ports rather than
a disjoint port pair: there is no disjoint pair available to use.

Stateful: generates real traffic on shared hardware, then probes a
control path (an action against a wholly separate object) no other test
in this suite has exercised. Never run alongside other stateful tests (no
xdist, no parallel stateful runs, per CLAUDE.md).

Selector notes carried over from every sibling in this file's family:
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the per-port line-rate
row lookup uses a start-anchored regex to survive the "UNIT" column added
to the wizard's Ports table.

Process note on this test's own dry runs (disclosed for transparency, same
spirit as `test_t10_clone_while_active.py`'s own disclosure): several
invocations while developing this test failed on this test's own
selector/flow assumptions, not on anything about the live testbed —
(1) the initial "commit config" step assumed an "Apply" button (the
pattern every older sibling in this file's family documents), but this
box's current UI shows "Save" + "Start" directly on a brand-new draft's
action bar with no separate "Apply"/"Deactivate" step, confirmed by a
debug screenshot before adjusting the code; (2) a lingering success toast
intercepted the "← Dashboard" click for its full timeout on a couple of
attempts; (3) the real root cause of the persistent "stayed INACTIVE"
failures: clicking "Start" pops a one-time confirmation dialog ("Testbed
is Inactive — Start will activate ... then run traffic ... Cancel /
Continue") that nothing in this test dismissed, so Start silently never
took effect — found by writing a dedicated standalone investigation
script (outside pytest) that logged in with the suite's own saved session
state and polled the page every 3s after clicking Start, rather than
continuing to guess through full stateful pytest re-runs; (4) that same
script also caught a second, more subtle issue once the dialog was
handled — a fixed-string `get_by_text("INACTIVE", exact=True)` wait
never matched anything real (Playwright's text locators match raw DOM
text, and the actual node reads lowercase "inactive" even though CSS
`text-transform` renders it visually as uppercase — `page.inner_text()`
reflects the rendered case, `get_by_text` doesn't), so the wait was a
silent no-op that let an earlier attempt navigate away before activation
had truly finished. The same script established empirically that the
real inactive→active transition lands within ~20s of dismissing the
dialog. Every one of these dry runs left T10-LiveCtrl/T10-Probe INACTIVE
or nonexistent — never disturbed a genuinely live run and never left
hardware in a bad state — confirmed via a manual state read + targeted
cleanup script after each, before the real, recorded run below.

--- RESULT (2026-09-15, one real recorded run against 192.168.173.111) ---

THE ALARMING OUTCOME. `T10-LiveCtrl` WAS disturbed by an action that
never referenced it in any way, and the disturbance looks WORSE than
either sibling bug, not merely equivalent:

  - `T10-LiveCtrl` was built, activated, and confirmed genuinely
    transmitting before anything else happened: the Per-Port Aggregate
    Statistics row for Port 3 showed real, climbing counters (867/868
    Tx/Rx frames, 193.6K bytes, nonzero rates) — not just a rendered Stop
    button.
  - `T10-Unrelated` was then created as a fresh draft (confirmed by its
    own tile appearing) and, before deleting it, its own Ports step was
    read directly and confirmed both Port 3 and Port 4 showed USE
    disabled — this mutation genuinely never touched the live testbed's
    ports, its ID, or its name at any point. It was then deleted
    (confirmed by its tile disappearing). Two real, completed backend
    writes, zero relationship to `T10-LiveCtrl`.
  - Immediately afterward — 32.9s into `T10-LiveCtrl`'s 90s configured
    hold, nowhere near natural completion — its dashboard tile showed
    NEITHER `Stop` NOR `Stats`. That second part is the more alarming
    detail: `test_t10_edit_config_while_active.py` and
    `test_t10_clone_while_active.py` both found the live testbed's `Stop`
    button disappear early, but in both of those the testbed remained in
    an ACTIVE-but-idle state afterward (tile still showed `Stats`/`Start`
    — an applied testbed that had merely stopped transmitting). Here,
    `Stats` was gone too, which reads as `T10-LiveCtrl` having dropped out
    of ACTIVE state entirely — closer to reverting to a plain draft than
    to "stopped early." This was captured via the test's own direct,
    role-based reads of the tile immediately after a confirmed-successful
    dashboard navigation (no toast-fallback `page.goto` occurred on this
    path this run — see the `[nav]` log line's absence — ruling out a
    stale-render artifact from that navigation helper).
  - Because the core assertion failed at this point, this run does not
    have direct evidence for the deeper checks the Edit/Clone siblings
    also captured (a Port 3 counter reset, an empty run-history Result
    cell) — the same disclosed gap `test_t10_clone_while_active.py`
    accepted when ITS leading symptom raised first. Per this task's
    explicit instruction, this test was not modified afterward to dig
    further or to force a pass; the box was confirmed fully clean
    (`T10-LiveCtrl`/`T10-Unrelated` both gone, Port 3/4 both `Available`)
    via this test's own teardown immediately after.

Net effect — this REQUIRES widening the existing "Confirmed product
issues" entry, not just adding a third trigger under it. As written, that
entry's mechanism is "a write referencing the specific live testbed"
(Edit+Save on it, or Clone reading it). This result shows a write with
ZERO reference to the live testbed — not its ID, not its name, not its
ports — still disrupted it, and arguably more severely (full drop from
ACTIVE, not just early Stop). The honest reading is that the backend
issue is not "mutating a testbed disrupts that testbed's own run," it's
closer to "any backend write while a run is in progress can disrupt
whatever happens to be live" — a systemic concern, not a scoped one, and
one that materially changes how this should be prioritized: it's not a
specific workflow to avoid (don't Edit or Clone a live testbed), it's a
general hazard of touching the UI/API at all while any run is active
anywhere on the box. This is a single run, not yet reproduced a second
time (deliberately — this task called for one genuine recorded attempt,
not iterating on shared hardware), so treat the *existence* of the
problem as demonstrated and its exact reproducibility as the natural next
question for a follow-up test, not yet established as "every time."

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest
from playwright.sync_api import Page

from pages import PortSpec, StreamSpec, TestbedSpec
from tests.t10_t12_lifecycle.known_issues import LIVE_RUN_INTERRUPTED

LIVE_NAME = "T10-LiveCtrl"
UNRELATED_NAME = "T10-Unrelated"
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.22.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.22.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(5, 90, 5),
)


@pytest.mark.stateful
@LIVE_RUN_INTERRUPTED
def test_t10_unrelated_action_during_live_run(dashboard: Page, traffic_engine):
    """Correct behaviour: creating and deleting an unrelated draft (no
    shared name, ID or ports) has no effect on a live run."""
    board = traffic_engine.dashboard
    traffic_engine.create(LIVE_NAME, SPEC)
    traffic_engine.start(LIVE_NAME)
    board.open()
    board.keeps_running(LIVE_NAME, 5)

    board.remove_testbed(UNRELATED_NAME)
    board.create_testbed(UNRELATED_NAME)
    board.remove_testbed(UNRELATED_NAME)

    board.keeps_running(LIVE_NAME, 30)
    board.tile_button(LIVE_NAME, "Stats").click()
    row = traffic_engine.runs.wait_for_run_to_finish(1, timeout=SPEC.run_seconds * 1000 + 180_000)
    traffic_engine.result(LIVE_NAME, row, expected_seconds=SPEC.run_seconds).assert_passed()
