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
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay short: the backend 502s on activate for any name
# over 15 chars (see project-bugs-found, 2026-09-09), and the product's
# own default clone name appends "-copy" — this name is sized so BOTH the
# original and its default clone name stay activatable.
TESTBED_NAME = "T10-CloneX"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _family_tiles(page: Page):
    """Matches the original AND any clone (whose default name is a
    superstring of TESTBED_NAME) — use for counting/existence checks."""
    return page.locator(".tb-tile").filter(has_text=TESTBED_NAME)


def _tile_by_exact_name(page: Page, name: str):
    """Disambiguates the original from a clone by the tile's own
    untruncated title attribute, rather than substring has_text."""
    return page.locator(".tb-tile").filter(has=page.locator(f'div[title="{name}"]'))


def _stop_if_live(page: Page, tile):
    stop_btn = tile.get_by_role("button", name="Stop", exact=True)
    if stop_btn.count() > 0 and stop_btn.is_visible():
        stop_btn.click()
        _buffer(page)
        expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=30000)


def _delete_tile(page: Page, tile):
    if tile.count() == 0:
        return
    _stop_if_live(page, tile)
    delete_btn = tile.locator('[data-tip="Delete"] button')
    if delete_btn.count() == 0:
        return
    delete_btn.click()
    _buffer(page)
    confirm = page.get_by_role("button", name="Delete", exact=True)
    if confirm.is_visible():
        confirm.click()
    expect(tile).to_have_count(0, timeout=10000)


def _delete_family_if_present(page: Page):
    """Deletes the original AND any clone(s) sharing TESTBED_NAME as a
    prefix — handles both the expected outcome (one clone) and an
    unexpected one (a stuck/duplicated clone)."""
    guard = 0
    while _family_tiles(page).count() > 0 and guard < 6:
        tile = _family_tiles(page).last
        _delete_tile(page, tile)
        guard += 1


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
    _delete_family_if_present(dashboard)
    yield
    _release_ports(dashboard)
    _delete_family_if_present(dashboard)
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
def test_t10_clone_while_active(dashboard: Page, clean_testbed):
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
    _family_tiles(page).get_by_role("button", name="Edit").click()
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
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.17.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.17.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.17.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.17.2")
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

    original_tile = _tile_by_exact_name(page, TESTBED_NAME)
    expect(original_tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)

    # --- Confirm traffic is genuinely flowing BEFORE touching the clone
    # icon — not just that the Stop button rendered.
    original_tile.get_by_role("button", name="Stats").click()
    row_text_before = None
    for _ in range(30):
        row_text_before = _read_port_row(page, "Port 3")
        if re.search(r"[1-9]", row_text_before):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(
            f"Port 3 row never showed nonzero traffic before the clone "
            f"attempt — can't call this a genuinely live run: {row_text_before!r}"
        )
    print(f"[clone-while-active] Port 3 row BEFORE clone (confirmed live): {row_text_before!r}")
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    original_tile = _tile_by_exact_name(page, TESTBED_NAME)
    expect(original_tile.get_by_role("button", name="Stop")).to_be_visible(timeout=10000)

    # --- The core of the test: click the duplicate/clone icon on the
    # LIVE, actively-transmitting testbed's tile. Case-insensitive
    # data-tip match rather than the exact known "Clone (without ports)"
    # string, in case the tooltip reads differently while live.
    clone_wrapper = original_tile.locator('[data-tip*="Clone" i]')
    clone_tip_text = clone_wrapper.get_attribute("data-tip") if clone_wrapper.count() > 0 else None
    clone_icon = clone_wrapper.locator("button")
    icon_present = clone_icon.count() > 0
    icon_visible = icon_present and clone_icon.is_visible()
    icon_disabled = icon_present and clone_icon.is_disabled()
    print(
        f"[clone-while-active] Clone icon on LIVE tile: present={icon_present} "
        f"visible={icon_visible} disabled={icon_disabled} tooltip={clone_tip_text!r}"
    )

    clone_created = False
    if not icon_present or not icon_visible or icon_disabled:
        print(
            "[clone-while-active] FINDING: the clone/duplicate icon is "
            "absent/hidden/disabled on a LIVE, actively-transmitting "
            "testbed tile — cloning is blocked while active at the "
            "control level. Clean, non-bug outcome; nothing further to "
            "probe here."
        )
    else:
        clone_icon.click()
        _buffer(page)

        # Does clicking pop the same "Clone '<name>' — New testbed name:
        # <prefilled>" confirm dialog documented for a draft testbed
        # (test_t4_duplicate_testbed.py), or does it behave differently
        # while the source is live?
        confirm_clone_btn = page.get_by_role("button", name="Clone", exact=True)
        dialog_appeared = confirm_clone_btn.count() > 0 and confirm_clone_btn.is_visible()
        clone_name_from_dialog = None
        if dialog_appeared:
            name_input = page.get_by_role("textbox")
            clone_name_from_dialog = name_input.input_value()
            print(
                f"[clone-while-active] Clone confirm dialog appeared, "
                f"product's own clone name: {clone_name_from_dialog!r} "
                f"({len(clone_name_from_dialog)} chars)"
            )
            confirm_clone_btn.click()
            _buffer(page)
        else:
            print(
                "[clone-while-active] No confirm dialog appeared after "
                "clicking the clone icon on the LIVE tile."
            )
            for dismiss_label in ["Close", "OK", "Cancel", "Got it"]:
                dismiss_btn = page.get_by_role("button", name=dismiss_label, exact=True)
                if dismiss_btn.count() > 0 and dismiss_btn.is_visible():
                    print(f"[clone-while-active] Dismissing unexpected modal via {dismiss_label!r}.")
                    dismiss_btn.click()
                    _buffer(page)
                    break

        page.wait_for_timeout(1500)
        tile_count = _family_tiles(page).count()
        print(f"[clone-while-active] Family tile count after clone attempt: {tile_count}")

        if tile_count < 2:
            print(
                "[clone-while-active] FINDING: clicking Clone on the LIVE "
                "tile did not produce a second testbed card — either the "
                "click was silently swallowed while active, or cloning "
                "failed without any visible error. No clone to inspect "
                "further."
            )
        else:
            clone_created = True
            title_divs = _family_tiles(page).locator("div[title]")
            found_names = {
                title_divs.nth(i).get_attribute("title") for i in range(title_divs.count())
            }
            print(f"[clone-while-active] Tile names present: {found_names!r}")
            assert TESTBED_NAME in found_names, (
                f"Original testbed {TESTBED_NAME!r} no longer has a tile "
                f"after the clone attempt — found {found_names!r} instead."
            )
            other_names = found_names - {TESTBED_NAME}
            assert len(other_names) == 1, (
                f"Expected exactly one new clone tile, found {other_names!r}"
            )
            clone_name = clone_name_from_dialog or next(iter(other_names))
            assert clone_name in other_names, (
                f"Clone name from the dialog ({clone_name!r}) doesn't match "
                f"the actual new tile's name ({other_names!r})"
            )
            print(f"[clone-while-active] Clone tile name: {clone_name!r} ({len(clone_name)} chars)")

            clone_tile = _tile_by_exact_name(page, clone_name)
            expect(clone_tile).to_have_count(1, timeout=10000)

            clone_buttons_text = clone_tile.locator("button").all_inner_texts()
            print(f"[clone-while-active] Clone tile action-bar button labels: {clone_buttons_text!r}")

            clone_has_stop = clone_tile.get_by_role("button", name="Stop", exact=True).count() > 0
            clone_has_start = clone_tile.get_by_role("button", name="Start", exact=True).count() > 0
            clone_has_activate = clone_tile.get_by_role("button", name="Activate", exact=True).count() > 0
            print(
                f"[clone-while-active] Clone state signals: "
                f"Activate={clone_has_activate} Start={clone_has_start} Stop={clone_has_stop}"
            )

            if clone_has_stop:
                raise AssertionError(
                    "REAL BUG: the CLONE of a live testbed came up already "
                    "TRANSMITTING (its tile shows a Stop button) despite "
                    "this test never clicking Activate or Start on it. "
                    "This is a worse variant of the already-confirmed "
                    "Edit-while-active bug (test_t10_edit_config_while_"
                    "active.py): there, editing a live testbed's config "
                    "corrupted the CURRENT run; here, merely cloning a "
                    "live testbed appears to have spawned a SECOND, "
                    "independently-live run the user never asked for."
                )
            if clone_has_start and not clone_has_activate:
                raise AssertionError(
                    "REAL BUG: the CLONE of a live testbed came up already "
                    "in an ACTIVE (applied) state — its tile shows "
                    "Start/Stats instead of Activate — despite this test "
                    "never clicking Activate on it. A clone should land as "
                    "a fresh inactive draft. Distinct from the "
                    "Edit-while-active bug (which corrupts the ORIGINAL's "
                    "run) — this is the clone itself inheriting state it "
                    "never earned."
                )
            assert clone_has_activate, (
                f"Clone tile shows neither Activate nor Start/Stop — "
                f"unrecognized state, button labels were {clone_buttons_text!r}"
            )
            print(
                "[clone-while-active] Clone landed as a fresh inactive "
                "draft (Activate present) — expected, sane outcome for "
                "this check."
            )

            # --- Does the clone's own config still reference Port 3/4 —
            # the same hardware ports the ORIGINAL is still actively
            # transmitting on? The tile's own tooltip claims "Clone
            # (without ports)"; verify that claim rather than trust it.
            clone_tile.get_by_role("button", name="Edit").click()
            _buffer(page)
            port_use_states = {}
            for port_label in PORTS:
                row = page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label)}\b"))
                rate_field = row.get_by_placeholder("line rate")
                is_disabled = rate_field.is_disabled()
                port_use_states[port_label] = not is_disabled
                print(
                    f"[clone-while-active] Clone Ports step — {port_label}: "
                    f"USE enabled={not is_disabled}"
                )

            page.get_by_role("button", name="← Dashboard").click()
            _buffer(page)
            discard_btn = page.get_by_role("button", name="Discard", exact=True)
            if discard_btn.is_visible():
                discard_btn.click()
            expect(page.get_by_text("Port Status")).to_be_visible(timeout=15000)

            carried_over = [p for p, v in port_use_states.items() if v]
            if carried_over:
                raise AssertionError(
                    f"REAL BUG: the clone's own Ports step shows USE "
                    f"enabled for {carried_over} — the SAME hardware "
                    "ports the ORIGINAL testbed is still actively "
                    "transmitting on — despite the clone icon's own "
                    "tooltip reading 'Clone (without ports)'. This is a "
                    "port-conflict-adjacent bug distinct from "
                    "test_t10_port_conflict_while_active.py (that test "
                    "covered two SEPARATE testbeds fighting over a port; "
                    "this is one testbed spawning a corrupted clone of "
                    "itself that references the same in-use ports)."
                )
            print(
                "[clone-while-active] Clone's Ports step shows both ports "
                "USE-disabled — confirms the 'without ports' tooltip "
                "claim; no port sharing with the live original."
            )

    # --- Was the ORIGINAL's live run disturbed purely by the clone
    # action? Same question the Edit-while-active sibling asked about
    # Save — this test never edits or saves the original itself, only
    # clicks its clone icon (and, if a clone was created, briefly opens
    # the CLONE's own Edit view — never the original's).
    original_tile = _tile_by_exact_name(page, TESTBED_NAME)
    original_still_live = original_tile.get_by_role("button", name="Stop").is_visible()
    print(f"[clone-while-active] ORIGINAL tile Stop visible after clone action: {original_still_live}")
    assert original_still_live, (
        "REAL BUG (same shape as the already-confirmed Edit-while-active "
        "finding in test_t10_edit_config_while_active.py): the ORIGINAL "
        "testbed's Stop button disappeared — its live run was disrupted "
        "— purely as a side effect of cloning it. Nothing was clicked on "
        "the original itself between confirming it was live and this "
        "check."
    )

    original_tile.get_by_role("button", name="Stats").click()
    row_text_after = _read_port_row(page, "Port 3")
    print(f"[clone-while-active] Port 3 row AFTER clone action: {row_text_after!r}")
    before_num = re.search(r"\d+", row_text_before)
    after_num = re.search(r"\d+", row_text_after)
    if before_num and after_num and int(after_num.group()) < int(before_num.group()):
        print(
            "[clone-while-active] FINDING: Port 3's leading counter looks "
            f"like it dropped ({before_num.group()} -> {after_num.group()}) "
            "rather than increased after the clone action — resembles the "
            "counter-reset pattern seen in the Edit-while-active bug, "
            "though Stop itself stayed visible here. Worth a dedicated "
            "follow-up if reproduced again."
        )
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Let the ORIGINAL run finish naturally, then confirm its
    # run-history Result wasn't lost — mirrors the Edit-while-active
    # sibling's final check exactly, same rationale (rule out the
    # population-race its own poll already guards against).
    original_tile = _tile_by_exact_name(page, TESTBED_NAME)
    if original_tile.get_by_role("button", name="Stop").is_visible():
        expect(original_tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=3 * 60 * 1000)

    original_tile = _tile_by_exact_name(page, TESTBED_NAME)
    reports_btn = original_tile.get_by_role("button", name="Reports:", exact=False)
    stats_btn = original_tile.get_by_role("button", name="Stats", exact=True)
    if reports_btn.is_visible():
        reports_btn.click()
    else:
        stats_btn.click()
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible(timeout=10000)
    cells = run_row.locator("td")
    expect(cells.nth(1)).not_to_have_text("")  # Started At
    expect(cells.nth(2)).not_to_have_text("")  # Duration
    result_text = ""
    for _ in range(40):
        result_text = cells.last.inner_text()
        if result_text.strip():
            break
        page.wait_for_timeout(500)
    print(f"[clone-while-active] ORIGINAL run-history row after the clone action: {result_text!r}")
    assert result_text.strip(), (
        "REAL BUG (same shape as Edit-while-active): the ORIGINAL "
        "testbed's run-history Result cell is empty after a generous 20s "
        "poll — the run's recorded outcome appears to have been lost, "
        "this time triggered merely by cloning the testbed while it was "
        "live, not by editing it."
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    print(f"[clone-while-active] clone_created={clone_created}")
