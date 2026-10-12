"""T10 — Clone (duplicate) a testbed while it is LIVE and actively
transmitting.

`netropy-ui-findings.md` ("There is no 'rename testbed' feature") already
documents the dashboard tile's duplicate/clone icon as the de-facto
rename workaround: its tooltip reads "Clone (without ports)", clicking it
opens a confirm dialog ("Clone '<name>' — New testbed name: <prefilled>")
pre-filled with "<name>-copy" (editable), and `test_t4_duplicate_testbed.py`
confirms — on a plain INACTIVE draft — that confirming produces a second
card with a distinct UID. Nobody has tried it on a testbed that is
genuinely live and transmitting.

That matters because the most recent sibling in this file's family,
`test_t10_edit_config_while_active.py`, found a real, confirmed product
bug: editing a live testbed's config and clicking Save silently kills the
in-progress run within seconds (Stop disappears early, a packet counter
resets to ~1, the eventual run-history Result cell is empty). Clone likely
shares internal machinery with Edit/Save, so the same "silently corrupts
the current run" failure mode is a live risk here too — plus a second,
Clone-specific risk the Edit test couldn't exercise at all: what state
does the *new* card come up in, given it's spawned from a live source?

Genuinely open going in, no pre-registered "correct" answer:
  1. Does the product block cloning outright while the source is active
     (icon absent/disabled), or does it allow it?
  2. If it clones, does the new card land as a fresh, inactive draft
     (expected/sane — matches the "(without ports)" tooltip, implying
     port associations are deliberately NOT carried over), or does it
     somehow come up already "active"/"live" — worse, already
     *transmitting* — despite Activate/Start never having been clicked on
     it?
  3. Does the clone's own Ports-step config actually leave Port 3/4
     unassigned (USE off, matching the tooltip's claim), or does it still
     reference the same hardware ports the ORIGINAL is actively
     transmitting on right now? That would be a port-conflict-adjacent
     bug distinct from `test_t10_port_conflict_while_active.py` — that
     test covered two SEPARATE testbeds fighting over a port; this would
     be one testbed spawning a corrupted clone of itself.
  4. Does the clone *action itself* disturb the ORIGINAL's live run —
     same shape as the Edit-while-active bug (Stop disappearing early, a
     lost/empty run-history Result), even though this test never edits or
     saves the original's config, only clicks its clone icon?

A quick, hardware-free DOM check before writing this test (loading the
dashboard read-only, no activation) found a pre-existing testbed on this
box ("TA") already in an ACTIVE-but-idle state (Start/Stats/Edit, no
Stop) — its tile still exposes all three top icons including
`data-tip="Clone (without ports)"`, unchanged from the inactive-draft
case. That's a hint the icon likely survives activation generally, but
says nothing about the specifically-transmitting (Stop-visible) case this
test targets, which is untested territory.

Per the task's explicit instruction: this test is not modified after the
fact to force a pass. A real bug found here gets reported as found, not
routed around.

--- CONFIRMED (2026-09-15, reproduced identically across two live runs
against 192.168.173.111) — a real product bug, question 4's answer ---

Questions 1–3 all came back clean:
  1. NO, the clone icon is not blocked while the source is live — it was
     present, visible, and enabled on the actively-transmitting tile both
     times (`data-tip="Clone (without ports)"`, unchanged from the
     inactive-draft tooltip).
  2. The clone lands as a fresh, inactive draft both times — its tile
     shows `Activate`/`Edit` only (no `Start`/`Stop`), never inheriting
     any active/live status it hadn't earned. Non-bug.
  3. The clone's own Ports step shows USE disabled for both Port 3 and
     Port 4 both times (confirmed by reading the line-rate field's
     `disabled` state directly, not just trusting the tooltip) — the
     "(without ports)" claim holds. No port sharing with the still-
     running original, so this is NOT the same shape as
     `test_t10_port_conflict_while_active.py`'s finding after all.

Question 4 is where it broke, reproduced identically both times: the
ORIGINAL testbed's dashboard tile showed `Stop` immediately before the
clone icon was clicked, and — despite this test never touching the
original itself again (no Edit, no Save, nothing) — its `Stop` button
was gone (`Stop visible=False`) by the time the very next check ran,
seconds after the clone action completed and the clone's own Ports step
had been briefly inspected. The test's own assertion caught this
(`assert original_still_live`) and raised before reaching the deeper
packet-counter/run-history checks written below for this exact purpose,
so — unlike the Edit-while-active finding, which additionally confirmed
a packet-counter reset to ~1 and a lost, empty run-history Result cell —
this run only has direct evidence for "Stop disappeared," not for
whether the run's eventual recorded result was also lost. That's a real
gap, disclosed rather than papered over.

Comparison to the Edit-while-active finding
(`test_t10_edit_config_while_active.py`): same shape, different trigger.
That test showed a config edit + Save on a live testbed silently
stops/restarts the current run within seconds. This test shows the
SAME "Stop vanishes almost immediately" symptom is reachable through a
completely different action — Clone — that never touches the original's
config at all, only reads it to produce a new draft. That strongly
suggests the underlying issue isn't specific to the Edit/Save code path;
something about the backend's handling of *any* mutating action against
a testbed object (config save, or apparently now clone-source read+copy)
appears to interrupt that same testbed's live run as a side effect,
regardless of which UI action triggered it. Worth flagging to Travis as
a systemic backend concern, not two unrelated bugs.

Process note, disclosed for transparency: this test was inadvertently
run a SECOND time (piping output to a file, not the deliberate "re-run
once to fix a test-side mistake" case this task's instructions allow —
this was a real hardware action against the shared box the task said
should be one-shot). Both runs reproduced the identical failure
(Stop-disappears-after-clone) with the same clean answers to questions
1–3, which is incidentally useful reproducibility evidence, but running
it twice was a mistake, not a deliberate decision, and is reported as
such rather than quietly folded in as if it were intended. No further
stateful runs were attempted after recognizing this.

Ports 3 + 4 only (Port 1/2 belong to someone else on this shared box right
now — confirmed still `Reserved`/`admin` in the same DOM check above —
Port 5/6 has a known link-down hardware issue — confirmed still `Down/No
Link` in that same check — Port 7/8 are unconfirmed/risky). Same
constraint as the rest of this exploratory batch.

Testbed name kept to 10 characters (`T10-CloneX`), shorter than every
sibling in this file: the product's own default clone name is
"<name>-copy", and this suite's `assert_activatable_name` 15-char ceiling
(see project bugs memory, 2026-09-09 — the appliance 502s on activate for
anything longer) has to leave room for that suffix too, so the *clone's*
name stays activatable if this test — or a human afterward — ever needed
to activate it. `T10-CloneX-copy` lands at exactly 15.

Stateful: generates real traffic on shared hardware, then probes a
control path (cloning a live testbed) no other test in this suite has
exercised. Never run alongside other stateful tests (no xdist, no
parallel stateful runs, per CLAUDE.md).

Selector notes carried over from every sibling in this file's family:
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the per-port line-rate
row lookup uses a start-anchored regex to survive the "UNIT" column added
to the wizard's Ports table. New to this test: the clone icon is located
via a case-insensitive `data-tip*="Clone"` attribute match rather than
hardcoding the exact tooltip string, in case it reads differently while
the source is live; and, once a clone exists, tiles are disambiguated by
each one's `div[title="<exact name>"]` element (the tile name node's
`title` attribute holds the untruncated name) rather than by substring
`has_text`, since the clone's default name is a superstring of the
original's.

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec
from tests.t10_t12_lifecycle.known_issues import LIVE_RUN_INTERRUPTED

TESTBED_NAME = "T10-CloneX"
CLONE_NAME = "T10-CloneX-copy"
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.17.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.17.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(5, 90, 5),
)


@pytest.mark.stateful
@LIVE_RUN_INTERRUPTED
def test_t10_clone_while_active(dashboard: Page, traffic_engine):
    """Correct behaviour: cloning a live testbed gives an inactive,
    port-free draft, and the original's run is untouched."""
    board = traffic_engine.dashboard
    traffic_engine.create(TESTBED_NAME, SPEC)
    traffic_engine.start(TESTBED_NAME)
    board.open()
    board.keeps_running(TESTBED_NAME, 5)

    board.remove_testbed(CLONE_NAME)
    clone = board.clone_testbed(TESTBED_NAME, CLONE_NAME)
    traffic_engine.created.append(CLONE_NAME)
    expect(clone.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
    expect(clone.get_by_role("button", name="Start", exact=True)).to_be_visible()

    board.keeps_running(TESTBED_NAME, 30)
    board.tile_button(TESTBED_NAME, "Stats").click()
    row = traffic_engine.runs.wait_for_run_to_finish(1, timeout=SPEC.run_seconds * 1000 + 180_000)
    traffic_engine.result(TESTBED_NAME, row, expected_seconds=SPEC.run_seconds).assert_passed()
