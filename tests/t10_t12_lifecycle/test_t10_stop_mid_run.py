"""T10 — Stop mid-run: every other lifecycle test in this suite only lets a
run finish on its own (ramp up → hold → ramp down → natural completion).
None of them exercise the dashboard tile's "Stop" button while traffic is
still actively flowing — this is the "Stop mid-run → run ends, result
recorded" item from the T10 plan section, still untested as of 2026-09-08.

Uses a deliberately long hold phase (3/60/3 = 66s total) so Stop is clicked
solidly mid-run (~13s in, ~53s before natural completion would occur) —
if the Stop button disappears quickly afterward, that's real evidence the
click actually ended the run rather than coincidentally lining up with
natural completion.

Ports 1+2, UDP, 1500-byte frames, 1 Gbps — same low-risk profile as the
UDP sibling test, since this test's point is the Stop control, not stream
config.

Stateful: generates real traffic on shared hardware, then interrupts it.

NTG 5.0 rewrite (2026-09-30): built with the shared conftest helpers;
started via Start -> "Testbed is Inactive" -> Continue (no Apply step).
The dashboard tile still has Stop while traffic runs. A manually stopped
run is saved with a "MANUAL STOP" end-reason chip in its Duration cell —
asserted here as direct evidence Stop ended the run.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED_NAME = "T10-StopMidRun"
# 3/60/3 = 66s, a long hold so Stop lands solidly mid-run.
SPEC = TestbedSpec(
    ports={1: PortSpec(rate=1), 2: PortSpec(rate=1)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(3, 60, 3),
)


@pytest.mark.stateful
def test_t10_stop_mid_run_ends_run_and_records_result(dashboard: Page, traffic_engine):
    page, board = dashboard, traffic_engine.dashboard
    traffic_engine.create(TESTBED_NAME, SPEC)
    traffic_engine.start(TESTBED_NAME)

    board.open()
    expect(board.is_running(TESTBED_NAME)).to_be_visible(timeout=15_000)
    # ~10s into the hold: clear of ramp-up and of the 66s natural end.
    page.wait_for_timeout(10_000)
    # The point of the test: Stop ends the run promptly, not ~50s later at
    # natural completion.
    board.stop_from_tile(TESTBED_NAME, timeout=20_000)

    board.tile_button(TESTBED_NAME, "Stats").click()
    row = traffic_engine.runs.wait_for_run_to_finish(run_number=1, timeout=30_000)
    expect(row).to_contain_text(re.compile(r"manual stop", re.I))
    # Summary sheet: traffic flowed before the stop. No run-length check:
    # it was stopped early on purpose.
    result = traffic_engine.result(TESTBED_NAME, row, label="stopped")
    assert not result.metrics.failed_checks(), result.metrics.failed_checks()
