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
TESTBED_NAME = "T10-StopMidRun"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_stop_mid_run_ends_run_and_records_result(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)
    enable_ports(page, PORTS, rate="1", unit="Gbps")
    add_stream(page, "UDP")
    set_all_frame_sizes(page, 1500)
    # 3/60/3 = 66s — a long hold so Stop lands solidly mid-run.
    set_ramp(page, up=3, hold=60, down=3)
    start_testbed(page)

    go_to_dashboard(page)
    tile = testbed_tile(page, TESTBED_NAME)
    stop = tile.get_by_role("button", name="Stop", exact=True)
    expect(stop).to_be_visible(timeout=15_000)
    # ~10s into the hold — clear of ramp-up and of the 66s natural end.
    page.wait_for_timeout(10_000)
    stop.click()

    # The point of the test: Stop ends the run promptly, not ~50s later at
    # natural completion.
    expect(stop).to_have_count(0, timeout=20_000)

    tile.get_by_role("button", name="Stats").click()
    run = wait_for_run_to_finish(page, run_number=1, timeout=30_000)
    expect(run).to_contain_text(re.compile(r"manual stop", re.I))
