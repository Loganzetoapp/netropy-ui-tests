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
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-EditLive"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400
ORIGINAL_FRAME_SIZE = "1500"
EDITED_FRAME_SIZE = "800"


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


def _read_port3_row(page: Page) -> str:
    """Must already be on the Statistics view. Returns Port 3's row text
    (label stripped) from the Per-Port Aggregate Statistics table."""
    per_port_heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(per_port_heading).to_be_visible(timeout=15000)
    per_port_table = per_port_heading.locator("xpath=following::table[1]")
    port3_row = per_port_table.get_by_role("row", name="Port 3", exact=False)
    return port3_row.inner_text().replace("Port 3", "")


@pytest.mark.stateful
def test_t10_edit_config_while_active(dashboard: Page, clean_testbed):
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
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.13.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.13.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.13.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.13.2")
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
    frame_size.fill(ORIGINAL_FRAME_SIZE)
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

    # --- Activate / Start ---
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)

    # --- Confirm traffic is genuinely flowing BEFORE touching anything,
    # not just that the Stop button rendered ---
    tile.get_by_role("button", name="Stats").click()
    row_text_before = None
    for _ in range(30):
        row_text_before = _read_port3_row(page)
        if re.search(r"[1-9]", row_text_before):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(
            f"Port 3 row never showed nonzero traffic before the edit "
            f"attempt — can't call this a genuinely live run: {row_text_before!r}"
        )
    print(f"[edit-while-active] Port 3 row BEFORE edit (confirmed live): {row_text_before!r}")

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- The core of the test: open Edit on the LIVE, actively-transmitting
    # testbed and try to change the Streams step's frame-size field ---
    tile.get_by_role("button", name="Edit").click()
    _buffer(page)
    # Confirm this really is the live post-Apply edit view (Deactivate
    # present), not some stale/reset draft — same check as
    # test_t10_deactivate_mid_run.py.
    expect(page.get_by_role("button", name="Deactivate", exact=True)).to_be_visible(timeout=15000)

    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    frame_size = page.locator("td:nth-child(5) > .fc").first
    expect(frame_size).to_be_visible(timeout=10000)

    value_while_live = frame_size.input_value()
    is_disabled = frame_size.is_disabled()
    is_readonly = frame_size.get_attribute("readonly") is not None
    print(
        f"[edit-while-active] Streams frame-size field while LIVE: "
        f"value={value_while_live!r} disabled={is_disabled} readonly={is_readonly}"
    )
    assert value_while_live == ORIGINAL_FRAME_SIZE, (
        f"Expected the live edit view to show the frame size this run was "
        f"actually started with ({ORIGINAL_FRAME_SIZE!r}), got "
        f"{value_while_live!r} — the edit view may be showing stale or "
        f"wrong data for this testbed."
    )

    edit_was_blocked = is_disabled or is_readonly
    save_label = None
    error_texts = []

    if edit_was_blocked:
        print(
            "[edit-while-active] FINDING: frame-size field is "
            f"disabled/readonly while active (disabled={is_disabled}, "
            f"readonly={is_readonly}) — editing is blocked at the field "
            "level. Clean, non-bug outcome."
        )
    else:
        frame_size.fill(EDITED_FRAME_SIZE)
        _buffer(page)
        frame_size.press("Enter")
        _buffer(page)
        value_after_typing = frame_size.input_value()
        print(
            f"[edit-while-active] Field accepted typed input while LIVE: "
            f"now reads {value_after_typing!r} (typed {EDITED_FRAME_SIZE!r})"
        )

        save_btn = page.get_by_role("button", name="Save", exact=True)
        apply_btn = page.get_by_role("button", name="Apply", exact=True)
        if save_btn.count() > 0 and save_btn.is_visible():
            save_target, save_label = save_btn, "Save"
        elif apply_btn.count() > 0 and apply_btn.is_visible():
            save_target, save_label = apply_btn, "Apply"
        else:
            save_target = None

        assert save_target is not None, (
            "Frame-size field was editable and accepted a new value while "
            "the testbed was LIVE, but neither a 'Save' nor an 'Apply' "
            "control was found in the action bar to attempt committing "
            "it — can't tell whether this state is even savable."
        )
        print(f"[edit-while-active] Clicking {save_label!r} to attempt committing the mid-run edit")
        save_target.click()
        _buffer(page)
        page.wait_for_timeout(2000)  # let any backend round-trip / toast land

        error_locator = page.get_by_text(
            re.compile(
                r"cannot|can.t|not allowed|error|failed|while (the testbed is )?active|while running",
                re.I,
            )
        )
        for i in range(min(error_locator.count(), 5)):
            error_texts.append(error_locator.nth(i).inner_text())
        print(f"[edit-while-active] Error/warning-like text visible after {save_label} attempt: {error_texts!r}")

        # Re-read the field in place (still on this page) to see whether
        # the click actually registered as a save vs a no-op.
        value_after_save_click = frame_size.input_value() if frame_size.is_visible() else None
        print(f"[edit-while-active] Frame-size field immediately after {save_label} click: {value_after_save_click!r}")

    # --- Did clicking Save/Apply pop an unexpected "unsaved changes"
    # prompt when leaving — would itself mean the save didn't register ---
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    dashboard_btn.click()
    _buffer(page)
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    unsaved_prompt_appeared = discard_btn.is_visible()
    if unsaved_prompt_appeared:
        print(
            f"[edit-while-active] FINDING: an 'Unsaved changes' prompt "
            f"appeared navigating away right after clicking {save_label!r} "
            "— the save click did not actually commit."
        )
        # Discard rather than silently re-attempting Save via a different
        # path — this is exploratory documentation, not a workaround.
        discard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=15000)

    # --- Is the run (and the testbed) still in a sane, non-corrupted
    # state on the dashboard? ---
    tile = _testbed_tile(page)
    still_shows_stop = tile.get_by_role("button", name="Stop").is_visible()
    still_active = tile.get_by_role("button", name="Stats").is_visible()
    print(
        f"[edit-while-active] Dashboard tile after edit attempt: "
        f"Stop visible={still_shows_stop}, still ACTIVE (Stats present)={still_active}"
    )
    assert still_active, (
        "Testbed dropped out of ACTIVE state (Stats button gone) purely as "
        "a side effect of the mid-run edit/save attempt — the testbed was "
        "never explicitly Deactivated or Stopped by this test at this point."
    )

    # --- If still transmitting, compare the live Per-Port row again to see
    # whether the edit visibly changed the CURRENT run's behavior ---
    if not edit_was_blocked:
        tile.get_by_role("button", name="Stats").click()
        row_text_after = _read_port3_row(page)
        print(f"[edit-while-active] Port 3 row AFTER {save_label} attempt: {row_text_after!r}")
        page.get_by_role("button", name="← Dashboard").click()
        expect(page.get_by_text("Port Status")).to_be_visible()
        tile = _testbed_tile(page)

    # --- Let the run finish naturally (if it hasn't already) rather than
    # tearing down mid-run — this is what lets us check whether the
    # eventual recorded result was corrupted by the edit attempt. ---
    if tile.get_by_role("button", name="Stop").is_visible():
        expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=3 * 60 * 1000)

    # --- Re-open Edit once more, post-completion, to see whether the typed
    # value actually persisted server-side (not just echoed back in the
    # same DOM node without a real round trip) ---
    if not edit_was_blocked:
        tile.get_by_role("button", name="Edit").click()
        _buffer(page)
        page.get_by_role("button", name="3 Streams traffic flows — at").click()
        _buffer(page)
        frame_size = page.locator("td:nth-child(5) > .fc").first
        expect(frame_size).to_be_visible(timeout=10000)
        persisted_value = frame_size.input_value()
        print(
            f"[edit-while-active] Frame-size field re-read after a fresh "
            f"navigation (post-run): {persisted_value!r} "
            f"(typed {EDITED_FRAME_SIZE!r}, original {ORIGINAL_FRAME_SIZE!r})"
        )
        if persisted_value == EDITED_FRAME_SIZE:
            print(
                "[edit-while-active] FINDING: the mid-run edit persisted "
                "server-side. Whether that's a bug depends on whether it "
                "touched the CURRENT run (see the before/after Port 3 rows "
                "above and the run-history check below) or only queues for "
                "the next run (legitimate, non-bug outcome)."
            )
        elif persisted_value == ORIGINAL_FRAME_SIZE:
            print(
                "[edit-while-active] FINDING: the mid-run edit did NOT "
                "persist — reverted back to the original value. The "
                f"{save_label} click while active was effectively a no-op "
                "for this field, whatever it appeared to do in the moment."
            )
        else:
            raise AssertionError(
                f"Frame-size field reads a THIRD, unexpected value "
                f"({persisted_value!r}) after the run completed — neither "
                f"the original ({ORIGINAL_FRAME_SIZE!r}) nor the edited "
                f"({EDITED_FRAME_SIZE!r}) value. That's its own anomaly."
            )
        page.get_by_role("button", name="← Dashboard").click()
        _buffer(page)
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=15000)
        tile = _testbed_tile(page)

    # --- Run history: was the eventual result recorded at all, and does
    # it look sane (not corrupted, not empty)? "Reports: N" only appears
    # once deactivated; "Stats" is what an active-but-idle testbed shows
    # instead (see netropy-ui-findings.md, "stats view and Reports badge
    # only exist in specific activation states") — check via whichever is
    # actually present rather than assuming deactivation happened.
    reports_btn = tile.get_by_role("button", name="Reports:", exact=False)
    stats_btn = tile.get_by_role("button", name="Stats", exact=True)
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
    # appear (up to 10s) rather than reading it once — the result value is
    # known to populate a moment after a run ends, not necessarily the
    # instant the row itself renders. Poll here too (a generous 20s) before
    # treating an empty cell as a real finding rather than that same race.
    result_text = ""
    for _ in range(40):
        result_text = cells.last.inner_text()
        if result_text.strip():
            break
        page.wait_for_timeout(500)
    print(f"[edit-while-active] Run-history row after the edit attempt: {result_text!r}")
    assert result_text.strip(), (
        "The Result cell for this run is still empty after a generous 20s "
        "poll (ruling out the population-race the UDP reference test's own "
        "PASS check guards against) — the run's recorded outcome appears "
        "to have been genuinely lost following the mid-run edit attempt."
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
