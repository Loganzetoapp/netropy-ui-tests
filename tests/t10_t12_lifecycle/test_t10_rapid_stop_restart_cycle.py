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

NTG 5.0 rewrite (2026-09-30): there's no Apply step any more. The
testbed is built and Saved once, then every cycle uses the dashboard
tile's Start. Cycle 1's Start shows the "Testbed is Inactive" popup
(Continue activates + starts); cycles 2 and 3 start the already-active,
synced testbed directly with no popup — start_testbed() handles both. So
activation still happens exactly once, as before.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import (
    add_stream,
    assert_activatable_name,
    create_testbed,
    enable_ports,
    go_to_dashboard,
    open_editor,
    remove_testbed,
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    testbed_tile,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-RapidCycle"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


def _start_and_confirm_live(page: Page, tile):
    """Start from the tile and confirm it really goes live (Stop appears)."""
    start = tile.get_by_role("button", name="Start", exact=True)
    expect(start).to_be_visible(timeout=10_000)
    start_testbed(page, start_button=start)
    expect(tile.get_by_role("button", name="Stop", exact=True)).to_be_visible(timeout=15_000)


def _confirm_traffic_flowing(page: Page, tile, port_label: str):
    """Open live Stats and confirm `port_label`'s Per-Port Aggregate row
    goes nonzero (not frozen at 0 after a restart), then come back."""
    tile.get_by_role("button", name="Stats").click()
    heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(heading).to_be_visible(timeout=15_000)
    row = heading.locator("xpath=following::table[1]").get_by_role(
        "row", name=re.compile(rf"^{re.escape(port_label)}\b")
    )
    text = ""
    for _ in range(30):
        text = row.inner_text()
        if re.search(r"[1-9]", text.replace(port_label, "")):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(f"{port_label} row never showed nonzero traffic after restart: {text!r}")
    go_to_dashboard(page)


def _stop_and_confirm_ended(tile):
    stop = tile.get_by_role("button", name="Stop", exact=True)
    stop.click()
    expect(stop).to_have_count(0, timeout=20_000)


@pytest.mark.stateful
def test_t10_rapid_stop_restart_cycle(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)
    enable_ports(page, PORTS, rate="1", unit="Gbps")
    add_stream(page, "UDP")
    set_all_frame_sizes(page, 1500)
    # 5/120/5 = 130s — room to interrupt twice well clear of natural end.
    set_ramp(page, up=5, hold=120, down=5)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Save", exact=True)).to_be_disabled(timeout=15_000)
    go_to_dashboard(page)
    tile = testbed_tile(page, TESTBED_NAME)

    # Cycle 1: Start (popup -> activate), confirm live, Stop mid-hold.
    _start_and_confirm_live(page, tile)
    _confirm_traffic_flowing(page, tile, "Port 3")
    page.wait_for_timeout(15_000)
    _stop_and_confirm_ended(tile)

    # Cycle 2: restart the SAME still-active tile — no deactivate, no edit.
    _start_and_confirm_live(page, tile)
    _confirm_traffic_flowing(page, tile, "Port 3")
    page.wait_for_timeout(15_000)
    _stop_and_confirm_ended(tile)

    # Cycle 3: restart once more and let it finish naturally.
    _start_and_confirm_live(page, tile)
    _confirm_traffic_flowing(page, tile, "Port 3")
    expect(tile.get_by_role("button", name="Stop", exact=True)).to_have_count(0, timeout=200_000)

    # Run history: exactly one clean row per cycle, three distinct starts.
    tile.get_by_role("button", name="Stats").click()
    wait_for_run_to_finish(page, run_number=3, timeout=30_000)
    started = set()
    for n in (1, 2, 3):
        row = page.get_by_role("row").filter(has_text=re.compile(rf"^\s*#{n}(?!\d)"))
        expect(row).to_have_count(1)
        expect(row.get_by_text(re.compile(r"^(pass|fail)$", re.I))).to_be_visible()
        started.add(row.locator("td").nth(1).inner_text().strip())
    assert len(started) == 3, f"expected 3 distinct Started At values, got {started}"
    expect(page.get_by_role("row").filter(has_text=re.compile(r"^\s*#4(?!\d)"))).to_have_count(0)
