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

Selector note: same caveats as the other lifecycle tests — several wizard
controls have no accessible name/role/data-testid and fall back to CSS
position (`.fc`, `.seg`, `nth-child`). The per-port line-rate row lookup
uses a start-anchored regex (not the old fixed suffix), matching the
2026-09-08 fix applied to the other lifecycle tests after a "UNIT" column
was added to the wizard's Ports table.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-StopMidRun"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]
BUFFER_MS = 400


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


@pytest.mark.stateful
def test_t10_stop_mid_run_ends_run_and_records_result(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 1 and Port 2 ---
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

    # --- Wizard step 1: Ports — enable Port 1 & Port 2, 1 Gbps line rate ---
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(1) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(2) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill("1")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 2\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.9.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.9.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.9.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.9.2")
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
    # 3/60/3 = 66s — a deliberately long hold phase so Stop can be clicked
    # solidly mid-run rather than racing natural completion.
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("3")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("60")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("3")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Confirm the run actually started, then interrupt it mid-hold ---
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    # ~10s into the hold phase (after the 3s ramp-up) — well clear of both
    # the ramp-up transient and the 66s natural-completion mark.
    page.wait_for_timeout(10000)
    tile.get_by_role("button", name="Stop").click()

    # --- The whole point of this test: Stop should end the run promptly,
    # not just coincide with the 66s natural completion (~53s away here).
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=20000)

    # --- Result recorded: testbed stays ACTIVE-but-idle after a manual
    # Stop (same as natural completion per prior T10/T11 findings), so the
    # run history is reached via "Stats", not the "Reports:" badge (that
    # only appears once the testbed is fully deactivated). Not asserting
    # a specific PASS/FAIL text here — the plan only calls for "result
    # recorded", and this test doesn't yet know what label a manually
    # stopped run carries; document whatever is found instead of assuming.
    tile.get_by_role("button", name="Stats").click()
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible(timeout=10000)
    cells = run_row.locator("td")
    expect(cells.nth(1)).not_to_have_text("")  # Started At
    expect(cells.nth(2)).not_to_have_text("")  # Duration
    result_text = cells.last.inner_text()
    assert result_text.strip(), "expected the Result cell to show some recorded outcome"

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
