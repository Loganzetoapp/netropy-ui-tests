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

from pages import DashboardPage, PortSpec, StreamSpec, TestbedSpec

TESTBED_NAME = "T10-RapidCycle"
# 5/120/5 = 130s: room to interrupt twice well clear of the natural end.
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1), 4: PortSpec(rate=1)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(5, 120, 5),
)


def _start_and_confirm_live(board: DashboardPage):
    """Start from the tile and confirm it really goes live (Stop appears)."""
    expect(board.tile_button(TESTBED_NAME, "Start")).to_be_visible(timeout=10_000)
    board.start_from_tile(TESTBED_NAME)
    expect(board.is_running(TESTBED_NAME)).to_be_visible(timeout=15_000)


def _confirm_traffic_flowing(page: Page, board: DashboardPage, port_label: str):
    """Open live Stats and confirm `port_label`'s Per-Port Aggregate row
    goes nonzero (not frozen at 0 after a restart), then come back."""
    board.tile_button(TESTBED_NAME, "Stats").click()
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
        page.wait_for_timeout(500)  # poll interval
    else:
        raise AssertionError(f"{port_label} row never showed nonzero traffic after restart: {text!r}")
    board.open()


@pytest.mark.stateful
def test_t10_rapid_stop_restart_cycle(dashboard: Page, traffic_engine):
    page, board = dashboard, traffic_engine.dashboard
    traffic_engine.create(TESTBED_NAME, SPEC)
    traffic_engine.editor.save()
    board.open()

    # Cycle 1: Start (popup -> activate), confirm live, Stop mid-hold.
    _start_and_confirm_live(board)
    _confirm_traffic_flowing(page, board, "Port 3")
    page.wait_for_timeout(15_000)
    board.stop_from_tile(TESTBED_NAME, timeout=20_000)

    # Cycle 2: restart the SAME still-active tile: no deactivate, no edit.
    _start_and_confirm_live(board)
    _confirm_traffic_flowing(page, board, "Port 3")
    page.wait_for_timeout(15_000)
    board.stop_from_tile(TESTBED_NAME, timeout=20_000)

    # Cycle 3: restart once more and let it finish naturally.
    _start_and_confirm_live(board)
    _confirm_traffic_flowing(page, board, "Port 3")
    expect(board.is_running(TESTBED_NAME)).to_have_count(0, timeout=200_000)

    # Run history: exactly one clean row per cycle, three distinct starts.
    board.tile_button(TESTBED_NAME, "Stats").click()
    runs = traffic_engine.runs
    runs.wait_for_run_to_finish(run_number=3, timeout=30_000)
    started = set()
    for n in (1, 2, 3):
        row = runs.run_row(n)
        expect(row).to_have_count(1)
        expect(row.get_by_text(re.compile(r"^(pass|fail)$", re.I))).to_be_visible()
        started.add(row.locator("td").nth(1).inner_text().strip())
    assert len(started) == 3, f"expected 3 distinct Started At values, got {started}"
    expect(runs.run_row(4)).to_have_count(0)

    # Summary sheet: the natural-length third run.
    result = traffic_engine.result(TESTBED_NAME, runs.run_row(3), label="cycle 3",
                                   expected_seconds=SPEC.run_seconds)
    assert not result.metrics.failed_checks(), result.metrics.failed_checks()
