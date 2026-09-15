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
"""
from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed names must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found,
# 2026-09-09). T10-Unrelated is never activated, but the rule is applied
# to it anyway per this task's instruction.
LIVE_NAME = "T10-LiveCtrl"
UNRELATED_NAME = "T10-Unrelated"
assert_activatable_name(LIVE_NAME)
assert_activatable_name(UNRELATED_NAME)

PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400
HOLD_SECONDS = 90


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _tile(page: Page, name: str):
    return page.locator(".tb-tile").filter(has_text=name)


def _goto_dashboard(page: Page):
    """Click '← Dashboard' and land back on it. A success toast (from a
    Save/Start/Delete a moment earlier) can sit over this button; a real
    (non-force) click can spend its whole timeout retrying against that
    overlay, and force=True is no safer here since Playwright still
    dispatches the click at real screen coordinates — whatever visually
    sits on top receives it, toast included. So: try a normal click
    first, and if the page hasn't actually navigated once that settles,
    fall back to a direct page.goto("/") rather than fight the overlay."""
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    try:
        dashboard_btn.click(timeout=8000)
    except Exception:
        print("[nav] '← Dashboard' click didn't land (likely a toast overlay) — falling back to page.goto('/')")
    _buffer(page)
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    if discard_btn.is_visible():
        discard_btn.click()
    if not page.get_by_text("Port Status").is_visible():
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)


def _stop_if_live(page: Page, tile):
    stop_btn = tile.get_by_role("button", name="Stop", exact=True)
    if stop_btn.count() > 0 and stop_btn.is_visible():
        stop_btn.click()
        _buffer(page)
        expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=30000)


def _delete_tile_if_present(page: Page, name: str):
    tile = _tile(page, name)
    if tile.count() == 0:
        return
    _stop_if_live(page, tile)
    delete_btn = tile.locator('[data-tip="Delete"] button')
    if delete_btn.count() == 0:
        delete_btn = tile.locator("button").nth(2)
    delete_btn.click()
    _buffer(page)
    confirm = page.get_by_role("button", name="Delete", exact=True)
    if confirm.is_visible():
        confirm.click()
    expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click(force=True)
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
def clean_testbeds(dashboard: Page):
    _delete_tile_if_present(dashboard, UNRELATED_NAME)
    _delete_tile_if_present(dashboard, LIVE_NAME)
    yield
    _release_ports(dashboard)
    _delete_tile_if_present(dashboard, UNRELATED_NAME)
    _delete_tile_if_present(dashboard, LIVE_NAME)
    # Explicit final hardware-state confirmation, per this task's
    # instruction to verify Port 3/4 are Available before finishing.
    for port_label in PORTS:
        row = dashboard.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=15000)


def _read_port_row(page: Page, port_label: str) -> str:
    """Must already be on the Statistics view. Returns the given port's
    row text (label stripped) from the Per-Port Aggregate Statistics
    table."""
    per_port_heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(per_port_heading).to_be_visible(timeout=15000)
    per_port_table = per_port_heading.locator("xpath=following::table[1]")
    row = per_port_table.get_by_role("row", name=port_label, exact=False)
    return row.inner_text().replace(port_label, "")


@pytest.mark.stateful
def test_t10_unrelated_action_during_live_run(dashboard: Page, clean_testbeds):
    page = dashboard

    # --- Reserve Port 3 and Port 4 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Build T10-LiveCtrl: UDP on Port 3+4 ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(LIVE_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 1 Gbps line rate ---
    _tile(page, LIVE_NAME).get_by_role("button", name="Edit").click()
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
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.22.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.22.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.22.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.22.2")
    _buffer(page)

    # --- Wizard step 3: Streams — UDP, 1500-byte frames ---
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

    # --- Wizard step 4: Traffic and Load Profile — 5/90/5 hold, plenty of
    # room to act mid-run before natural completion ---
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
    page.locator("div:nth-child(2) > .fc > input").fill(str(HOLD_SECONDS))
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("5")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)

    # --- Commit the config. On this box's current UI a brand-new draft's
    # action bar reads "Save" + "Start" directly (no separate "Apply" that
    # swaps to "Deactivate") — differs from what this file's siblings
    # (edit/clone-while-active, the UDP reference test) documented earlier
    # today, confirmed by direct inspection (screenshot) before adjusting
    # this rather than guessing. Handle either label for resilience.
    apply_btn = page.get_by_role("button", name="Apply", exact=True)
    save_btn = page.get_by_role("button", name="Save", exact=True)
    if apply_btn.count() > 0 and apply_btn.is_visible():
        apply_btn.click()
        commit_label = "Apply"
    elif save_btn.count() > 0 and save_btn.is_visible():
        save_btn.click()
        commit_label = "Save"
    else:
        raise AssertionError(
            "Neither an 'Apply' nor a 'Save' button is visible on the "
            "wizard's action bar after filling in all 4 steps — can't "
            "commit T10-LiveCtrl's config."
        )
    _buffer(page)
    print(f"[build] Committed T10-LiveCtrl's config via {commit_label!r} button")

    # --- Activate / Start ---
    start_btn = page.get_by_role("button", name="Start", exact=True)
    expect(start_btn).to_be_visible(timeout=75000)
    start_btn.click()
    start_time = time.monotonic()
    # Clicking Start can pop a one-time confirmation dialog ("Testbed is
    # Inactive — Start will activate ... on the unit, then run traffic ...
    # Cancel / Continue", with a "Don't show this again" option) —
    # confirmed live via a dedicated investigation script before adjusting
    # this: earlier dry runs of this test (see docstring's process note)
    # left the testbed permanently INACTIVE because nothing ever dismissed
    # it. Handle it if it appears; it may not (e.g. already dismissed for
    # this account).
    continue_btn = page.get_by_role("button", name="Continue", exact=True)
    try:
        continue_btn.click(timeout=5000)
        print("[build] Dismissed the one-time Start confirmation dialog")
    except Exception:
        print("[build] No Start confirmation dialog appeared")
    # Start's tooltip reads "Save, activate and run traffic" — a
    # save+activate+start round trip, not instant. An exact, case-matched
    # wait on the header's "INACTIVE" badge (get_by_text matches raw DOM
    # text, not the CSS text-transform: uppercase actually rendering it)
    # silently never matched anything and made an earlier dry run of this
    # test navigate away before activation had truly finished (see
    # docstring's process note) — the investigation script that caught
    # this observed the real transition landing consistently within
    # ~20s of dismissing the dialog. Give it real margin here, then let
    # the dashboard-tile check below (its own generous, role-based wait)
    # be the actual confirmation activation succeeded.
    page.wait_for_timeout(20000)
    _goto_dashboard(page)

    live_tile = _tile(page, LIVE_NAME)
    expect(live_tile.get_by_role("button", name="Stop")).to_be_visible(timeout=60000)

    # --- Confirm traffic is genuinely flowing BEFORE touching anything —
    # not just that the Stop button rendered ---
    live_tile.get_by_role("button", name="Stats").click()
    row_text_before = None
    for _ in range(30):
        row_text_before = _read_port_row(page, "Port 3")
        if re.search(r"[1-9]", row_text_before):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(
            f"Port 3 row never showed nonzero traffic before the unrelated "
            f"action — can't call this a genuinely live run: {row_text_before!r}"
        )
    print(f"[unrelated-action] Port 3 row BEFORE unrelated action (confirmed live): {row_text_before!r}")
    _goto_dashboard(page)

    live_tile = _tile(page, LIVE_NAME)
    expect(live_tile.get_by_role("button", name="Stop")).to_be_visible(timeout=10000)

    # --- The core of the test: perform a mutation against a SECOND, wholly
    # separate object — never references T10-LiveCtrl's name, ID, or ports.
    # Create a brand-new draft testbed and delete it again: two real
    # backend writes, zero port toggles ever clicked. ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(UNRELATED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    unrelated_tile = _tile(page, UNRELATED_NAME)
    expect(unrelated_tile).to_have_count(1, timeout=10000)
    print(f"[unrelated-action] {UNRELATED_NAME!r} created as a fresh draft — real backend write #1 done")

    # --- Verify the claim rather than trust it: the fresh draft's Ports
    # step should show every USE toggle off, specifically confirming Port
    # 3/4 (the live testbed's own ports) were never touched. ---
    unrelated_tile.get_by_role("button", name="Edit").click()
    _buffer(page)
    port_use_states = {}
    for port_label in PORTS:
        row = page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label)}\b"))
        rate_field = row.get_by_placeholder("line rate")
        is_disabled = rate_field.is_disabled()
        port_use_states[port_label] = not is_disabled
        print(
            f"[unrelated-action] {UNRELATED_NAME!r} Ports step — {port_label}: "
            f"USE enabled={not is_disabled}"
        )
    touched_ports = [p for p, v in port_use_states.items() if v]
    assert not touched_ports, (
        f"{UNRELATED_NAME!r}'s own Ports step shows USE enabled for "
        f"{touched_ports} — this draft was supposed to leave every port "
        "untouched, including the live testbed's own Port 3/4. The "
        "'unrelated' premise of this test doesn't hold if this failed."
    )

    _goto_dashboard(page)

    # --- Delete it — real backend write #2, still zero relationship to
    # T10-LiveCtrl. ---
    _delete_tile_if_present(page, UNRELATED_NAME)
    print(f"[unrelated-action] {UNRELATED_NAME!r} deleted — real backend write #2 done")

    elapsed_since_start = time.monotonic() - start_time
    print(f"[unrelated-action] Elapsed since T10-LiveCtrl Start: {elapsed_since_start:.1f}s (configured hold: {HOLD_SECONDS}s)")

    # --- Was T10-LiveCtrl's live run disturbed purely by the unrelated
    # create+delete? This is the entire point of the test. ---
    live_tile = _tile(page, LIVE_NAME)
    still_active = live_tile.get_by_role("button", name="Stats").is_visible()
    still_shows_stop = live_tile.get_by_role("button", name="Stop", exact=True).is_visible()
    print(
        f"[unrelated-action] T10-LiveCtrl tile right after the unrelated "
        f"action: Stop visible={still_shows_stop}, still ACTIVE (Stats "
        f"present)={still_active}"
    )

    assert still_active, (
        "T10-LiveCtrl dropped out of ACTIVE state (Stats button gone) "
        "purely as a side effect of creating and deleting a completely "
        "unrelated, zero-port draft testbed elsewhere on the box — this "
        "test never touched T10-LiveCtrl itself after confirming it was "
        "live. This would be a materially BIGGER finding than the "
        "existing Edit/Clone-while-active bug: it would mean the scope of "
        "'Confirmed product issues' needs to widen from 'a write "
        "referencing the specific live testbed' to 'any backend write at "
        "all while something is live.'"
    )

    row_text_after = None
    if still_shows_stop:
        live_tile.get_by_role("button", name="Stats").click()
        row_text_after = _read_port_row(page, "Port 3")
        print(f"[unrelated-action] Port 3 row AFTER unrelated action: {row_text_after!r}")
        before_num = re.search(r"\d+", row_text_before)
        after_num = re.search(r"\d+", row_text_after)
        if before_num and after_num and int(after_num.group()) < int(before_num.group()):
            print(
                "[unrelated-action] FINDING: Port 3's leading counter looks "
                f"like it dropped ({before_num.group()} -> {after_num.group()}) "
                "rather than increased — resembles the counter-reset pattern "
                "seen in the Edit/Clone-while-active bugs, even though this "
                "action never referenced T10-LiveCtrl at all."
            )
        _goto_dashboard(page)
    else:
        print(
            "[unrelated-action] FINDING: Stop vanished on T10-LiveCtrl "
            f"after only {elapsed_since_start:.1f}s of its {HOLD_SECONDS}s "
            "configured hold, purely as a side effect of an action against "
            "a completely separate, unrelated object."
        )

    assert still_shows_stop, (
        f"REAL BUG, BROADER THAN CURRENTLY DOCUMENTED: T10-LiveCtrl's Stop "
        f"button disappeared only {elapsed_since_start:.1f}s into its "
        f"{HOLD_SECONDS}s configured hold, immediately after creating and "
        "deleting a wholly unrelated draft testbed (T10-Unrelated) that "
        "never referenced T10-LiveCtrl's name, ID, or ports in any way, "
        "and never touched Port 3 or Port 4 (confirmed above). The "
        "existing 'Confirmed product issues' entry documents this symptom "
        "only for actions that reference the specific live testbed (Edit "
        "+ Save on it, or Clone reading it) — this result means that "
        "scope is too narrow: it looks like ANY backend write, anywhere, "
        "disrupts whatever happens to be live at the time. Flag this to "
        "Travis as a systemic backend concern with a much larger blast "
        "radius than currently written up, not a variant of the same "
        "narrow bug."
    )

    # --- Boundary confirmed so far (Stop survived). Let the run finish
    # naturally rather than tearing down mid-run, then confirm the eventual
    # recorded result is real and non-empty — full end-to-end confirmation
    # that the run was genuinely undisturbed, not merely that Stop hadn't
    # been reaped yet. ---
    live_tile = _tile(page, LIVE_NAME)
    if live_tile.get_by_role("button", name="Stop").is_visible():
        expect(live_tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=3 * 60 * 1000)

    live_tile = _tile(page, LIVE_NAME)
    reports_btn = live_tile.get_by_role("button", name="Reports:", exact=False)
    stats_btn = live_tile.get_by_role("button", name="Stats", exact=True)
    if reports_btn.is_visible():
        reports_btn.click()
    else:
        stats_btn.click()
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible(timeout=10000)
    cells = run_row.locator("td")
    expect(cells.nth(1)).not_to_have_text("")  # Started At
    expect(cells.nth(2)).not_to_have_text("")  # Duration
    # The UDP reference test's own PASS check polls for the Result text to
    # appear (up to 10s) rather than reading it once — poll here too (a
    # generous 20s) before treating an empty cell as a real finding.
    result_text = ""
    for _ in range(40):
        result_text = cells.last.inner_text()
        if result_text.strip():
            break
        page.wait_for_timeout(500)
    print(f"[unrelated-action] T10-LiveCtrl run-history row after the unrelated action: {result_text!r}")
    assert result_text.strip(), (
        "T10-LiveCtrl's Stop button survived the unrelated create+delete, "
        "but the eventual run-history Result cell is still empty after a "
        "generous 20s poll — a subtler form of the same corruption the "
        "Edit/Clone-while-active bugs produce, even without the early-Stop "
        "symptom. Worth flagging even though the leading symptom didn't "
        "reproduce."
    )

    _goto_dashboard(page)
