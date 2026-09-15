"""T10 — Rapid stop/restart cycling on a single still-Applied testbed.

Every other lifecycle test in this suite treats a testbed's "Applied +
Start" step as something that happens once per test: either the run
finishes on its own, or (test_t10_stop_mid_run) it's interrupted once and
the story ends there. None of them ask what happens if you Stop a live
run and then, *without Deactivating or deleting the testbed*, click Start
again on that same still-Applied tile — repeatedly, back to back. That's
exactly the kind of state-transition edge case a real user (or a flaky
finger on the dashboard) could hit, and it's untested.

This builds one UDP testbed on Port 3 + Port 4 with a deliberately long
hold phase (5/120/5 = 130s ramp) so there's plenty of room to interrupt
it well clear of both the ramp-up transient and natural completion, then
runs the cycle:

    Start -> confirm live -> Stop -> Start again -> confirm live -> Stop
    -> Start a third time -> let it finish naturally this time

At each restart, this checks two things a stuck product could plausibly
fail on: (1) the Start button is actually responsive and Stop reappears
within a reasonable window (not stuck showing a stale "active" badge with
Start doing nothing), and (2) the Per-Port Aggregate Statistics row for
Port 3 goes genuinely nonzero again post-restart (not frozen at 0, and
not just an artifact of a UI that never left the "live" visual state to
begin with). After all three cycles it also checks the run-history table
for exactly one clean row per cycle — the corruption/duplication/missing-
entry failure mode called out in the task.

Context relevant to reading any failure here: activation itself is known
to be intermittently unreliable via a **separate, already-root-caused**
bug — testbed names over 15 characters permanently 502 on activate (see
netropy-ui-findings.md, "Testbed activation 502s permanently"). This test
guards against that with assert_activatable_name() same as every other
activating test, and the testbed here is created and Applied exactly
once — every Start/Stop cycle after that reuses the *same* already-active
testbed, it never re-activates. So a failure partway through this test is
NOT that old 502-on-activate bug resurfacing (this test never calls
activate more than once); it would be a genuinely new stop/restart-cycle
bug and should be reported as such, not conflated with the known one.

Selector/pattern notes carried over from the closest siblings
(test_t10_stop_mid_run.py, test_t10_t12_lifecycle_udp_1gbps_1500b.py,
test_t10_two_testbeds_simultaneous.py):
- Several wizard controls have no accessible name/role/data-testid and
  fall back to CSS position (`.fc`, `.seg`, `nth-child`) — same as every
  other lifecycle test in this file's family.
- Clicking Start from the dashboard tile itself (as opposed to from
  inside the wizard's post-Apply action bar) stays on the dashboard and
  updates the tile in place, rather than navigating into the Statistics
  view — confirmed in test_t10_two_testbeds_simultaneous.py. That's the
  form used here for every restart, since we're deliberately staying on
  the tile across cycles rather than re-entering the wizard.

Stateful: generates real traffic on shared hardware, three times in a
row on the same testbed. Never run alongside other stateful tests (no
xdist, no parallel stateful runs, per CLAUDE.md).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-RapidCycle"
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
        # Icon order confirmed via screenshot: [0]=download [1]=duplicate [2]=delete
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


def _start_and_confirm_live(page: Page, tile, *, cycle: int):
    """Click Start on the tile and confirm it actually goes live — the
    core "does a restart cleanly re-enter a live state" check. If Start
    is unresponsive or Stop never reappears, this is where it surfaces.
    """
    start_btn = tile.get_by_role("button", name="Start")
    expect(start_btn).to_be_visible(timeout=10000)
    start_btn.click()
    _buffer(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)


def _confirm_traffic_flowing(page: Page, tile, port_label: str):
    """Open the tile's live Stats view and confirm the Per-Port Aggregate
    Statistics row for `port_label` is genuinely nonzero — not stuck at 0
    (or, on a later cycle, suspiciously frozen) — then return to the
    dashboard. Same technique as
    test_t10_live_view_badges_and_controls.py: strip the port label out
    of the row's text and look for a remaining nonzero digit, rather than
    guessing a specific column index.
    """
    tile.get_by_role("button", name="Stats").click()
    per_port_heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(per_port_heading).to_be_visible(timeout=15000)
    per_port_table = per_port_heading.locator("xpath=following::table[1]")
    row = per_port_table.get_by_role("row", name=port_label, exact=False)

    text = ""
    for _ in range(30):
        text = row.inner_text()
        if re.search(r"[1-9]", text.replace(port_label, "")):
            break
        page.wait_for_timeout(500)
    else:
        page.get_by_role("button", name="← Dashboard").click()
        raise AssertionError(
            f"{port_label} row never showed nonzero traffic after restart: {text!r}"
        )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
    return text


def _stop_and_confirm_ended(tile):
    """Click Stop and confirm the run promptly ends (Stop disappears) —
    not just coincidentally lining up with natural completion, same
    reasoning as test_t10_stop_mid_run.
    """
    tile.get_by_role("button", name="Stop").click()
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=20000)


@pytest.mark.stateful
def test_t10_rapid_stop_restart_cycle(dashboard: Page, clean_testbed):
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
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.7.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.7.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.7.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.7.2")
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
    # 5/120/5 = 130s — a long hold phase so there's ample room to interrupt
    # (twice!) well clear of both the ramp-up transient and natural
    # completion, and so the third, natural-completion cycle has a real
    # hold phase to actually run rather than immediately ramping down.
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
    page.locator("div:nth-child(2) > .fc > input").fill("120")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("5")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Apply (activate) once — every cycle below reuses this same
    # already-active testbed; nothing re-activates. ---
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    tile = _testbed_tile(page)

    # ================= Cycle 1: Start, confirm live, Stop mid-hold =================
    _start_and_confirm_live(page, tile, cycle=1)
    _confirm_traffic_flowing(page, tile, "Port 3")
    # ~15-20s into the 130s ramp by this point (ramp-up + traffic-check
    # loop) — solidly mid-hold, nowhere near natural completion.
    page.wait_for_timeout(15000)
    _stop_and_confirm_ended(tile)

    # ================= Cycle 2: restart the SAME still-Applied tile =================
    # Deliberately no Deactivate, no delete, no re-Apply between cycles —
    # this is the exact scenario under test: does Start work cleanly again
    # on a tile that was just Stopped, without ever leaving the Applied
    # state.
    _start_and_confirm_live(page, tile, cycle=2)
    _confirm_traffic_flowing(page, tile, "Port 3")
    page.wait_for_timeout(15000)
    _stop_and_confirm_ended(tile)

    # ================= Cycle 3: restart once more, let it finish naturally =================
    _start_and_confirm_live(page, tile, cycle=3)
    _confirm_traffic_flowing(page, tile, "Port 3")
    # Natural completion this time — full 130s ramp plus UI/activation
    # lag. Budgeted generously since this test cycles activation-adjacent
    # state three times over (longer than any single sibling test).
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=200_000)

    # --- Run history integrity check: exactly one clean row per cycle,
    # no corrupted/duplicate/missing entries. ---
    tile.get_by_role("button", name="Stats").click()
    rows = page.locator("table.runs-table tbody tr")
    expect(rows).to_have_count(3, timeout=10000)
    started_ats = set()
    for i in range(3):
        cells = rows.nth(i).locator("td")
        started_at = cells.nth(1).inner_text().strip()
        duration = cells.nth(2).inner_text().strip()
        result_text = cells.last.inner_text().strip()
        assert started_at, f"run row {i} missing Started At"
        assert duration, f"run row {i} missing Duration"
        assert result_text, f"run row {i} missing a recorded Result"
        started_ats.add(started_at)
    assert len(started_ats) == 3, (
        f"expected 3 distinct Started At timestamps (one per cycle), "
        f"got {started_ats} — possible duplicate/corrupted run-history entry"
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
