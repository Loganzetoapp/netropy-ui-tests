"""T10 — two testbeds running simultaneously on disjoint ports.

Explicitly called out in the plan's T10 section ("Two testbeds running
simultaneously on disjoint ports") but not yet covered by the single-
testbed lifecycle siblings (UDP on Port 3+4, TCP on Port 5+6, ICMP on
Port 1+2). This test builds and activates a UDP testbed on Port 1+2 and
a TCP testbed on Port 3+4, confirms both are live (Stop visible) at the
same time, waits for both to finish naturally, and asserts both PASS
independently — proving the product genuinely runs concurrent testbeds
rather than serializing them under the hood.

Port pair note (2026-08-26): originally used Port 3+4 / Port 7+8, but
Port 7+8 went Down/No Link after their first-ever activation while
developing this test — same symptom as the Port 5/6 incident on
2026-08-25 (see project_bugs_found memory), both times on a pair's
*first* activation. At Logan's direction, using only Port 1-4 (both
already exercised cleanly by the ICMP/UDP siblings) until 5-8 are
confirmed healthy again.

Both testbeds are fully built and Applied (configured + activated,
waiting at the Deactivate bar) *before* either is Started — Starting
both back-to-back this way, rather than fully running A to completion
before even starting to configure B, is what actually makes the runs
overlap in time. An earlier version of this test built+started A, then
built B while A ran; A's short ramp finished before B's ~90s of wizard
setup was even done, so they never actually overlapped — sequencing
bug, not a selector issue.

The wizard-filling steps happen sequentially in this script (Playwright
drives one page at a time), same as a human would. The actual
concurrency being verified is server-side — both testbeds' runs
overlapping in time — not simultaneous UI actions.

Stateful: generates real traffic on shared hardware, on two testbeds at
once. Never run alongside the other T10/T12 lifecycle tests (no xdist,
no parallel stateful runs, per CLAUDE.md) — this test's own two port
pairs are disjoint from each other, but it should still run alone
relative to other stateful tests.

Selector note: same caveats as the single-testbed siblings — several
wizard controls have no accessible name/role/data-testid and fall back
to CSS position (`.fc`, `.seg`, `nth-child`). See those files' docstrings
for the full rationale; not repeated here.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_A_NAME = "T10-Concur-A"
TESTBED_B_NAME = "T10-Concur-B"
assert_activatable_name(TESTBED_A_NAME)
assert_activatable_name(TESTBED_B_NAME)
PORTS_A = ["Port 1", "Port 2"]
PORTS_B = ["Port 3", "Port 4"]
ALL_PORTS = PORTS_A + PORTS_B
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _port_number(port_label: str) -> int:
    return int(port_label.split()[-1])


def _testbed_tile(page: Page, name: str):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_testbed_if_present(page: Page, name: str):
    tile = _testbed_tile(page, name)
    if tile.count() > 0:
        # Icon order confirmed via screenshot: [0]=download [1]=duplicate [2]=delete
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page, name)).to_have_count(0, timeout=10000)


def _release_ports(page: Page, ports):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal (Discard
        # / Save & close / Keep editing) that blocks the plain click above
        # from actually landing on the dashboard.
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in ports:
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
    _delete_testbed_if_present(dashboard, TESTBED_A_NAME)
    _delete_testbed_if_present(dashboard, TESTBED_B_NAME)
    yield
    _release_ports(dashboard, ALL_PORTS)
    _delete_testbed_if_present(dashboard, TESTBED_A_NAME)
    _delete_testbed_if_present(dashboard, TESTBED_B_NAME)


def _reserve_ports(page: Page, ports):
    for port_label in ports:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)


def _build_and_apply_testbed(
    page: Page,
    *,
    name: str,
    ports,
    ip_base: str,
    cidr: str,
    rate_gbps: int,
    protocol_button_name: str | None,
    frame_size: int,
    ramp,
):
    """Build a Traffic Engine testbed through the wizard and Apply
    (activate) it — stops right after the Deactivate bar appears, without
    clicking Start. Leaves the page back on the dashboard. Generalized
    over ports/IP/protocol/frame-size/ramp so it can build two different
    testbeds in one test; see _start_testbed for the separate Start step,
    kept apart so both testbeds can be built first and started back-to-
    back (see module docstring for why that ordering matters here).
    """
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(name)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # Always scope Edit to the testbed by name, never by position — a
    # positional index silently edits whichever tile happens to sit there.
    _testbed_tile(page, name).get_by_role("button", name="Edit").click()
    _buffer(page)
    for port_label in ports:
        n = _port_number(port_label)
        page.locator(f"tr:nth-child({n}) > td > div > .toggle > .track").click()
        _buffer(page)
    for port_label in ports:
        # Anchor on the port label at the start of the row's accessible
        # name rather than the old "{port} 10 Gbps ⚠ reserved by" literal
        # — a "UNIT" column (value "Local") was added between the port
        # name and the rate, breaking the contiguous substring match. A
        # start-anchor also disambiguates from other ports' rows, which
        # list this port as a Peer Port dropdown option elsewhere in
        # their own row text.
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill(str(rate_gbps))
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(rf"^{re.escape(ports[-1])}\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    ip1, ip2 = f"{ip_base}1", f"{ip_base}2"
    page.get_by_role("textbox", name="10.1.0.10").first.fill(ip1)
    _buffer(page)
    page.locator(".seg").first.select_option(cidr)
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill(ip2)
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option(cidr)
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill(ip1)
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill(ip2)
    _buffer(page)

    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    if protocol_button_name:
        # Only UDP is the picker's default-highlighted protocol; anything
        # else has to be selected explicitly.
        page.get_by_role("button", name=protocol_button_name, exact=True).click()
        _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    proto_label = protocol_button_name or "UDP"
    # Layer chip's accessible name combines label + tooltip (e.g. "TCP Edit
    # TCP"), not exact protocol name — use a substring role match.
    expect(page.get_by_role("button", name=f"{proto_label} Edit {proto_label}").first).to_be_visible()
    frame_size_field = page.locator("td:nth-child(5) > .fc").first
    frame_size_field.fill(str(frame_size))
    _buffer(page)
    frame_size_field.press("Enter")
    _buffer(page)

    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        # Toggle state wasn't what we assumed — click again to reach the
        # ramp-enabled state that actually exposes the input fields below.
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    up, hold, down = ramp
    page.locator(".fc > input").first.fill(str(up))
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill(str(hold))
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill(str(down))
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # The activate call itself carries a `?wait=15` server-side contract
    # and can legitimately take longer than 30s plus UI lag to resolve —
    # confirmed 2026-08-25 on the UDP sibling test — so give it real room.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)

    # Applying doesn't navigate away from the wizard/edit view on its own —
    # get back to the dashboard so the next testbed's "Create Testbed"
    # button (and this one's Start button, clicked later from the tile) are
    # reachable.
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()


def _start_testbed(page: Page, name: str):
    """Click Start on an already-Applied testbed's dashboard tile. Split
    out from building/Applying so two testbeds can be started back-to-back
    with minimal gap — see module docstring.

    Unlike clicking Start from inside the wizard's post-Apply action bar
    (which navigates into the Statistics view — see the single-testbed
    lifecycle siblings), clicking Start from the dashboard tile itself
    stays on the dashboard and updates the tile in place. Confirmed via a
    live diagnostic 2026-08-26: URL stayed at "/" after the click, no "←
    Dashboard" button ever appears because we never left the dashboard.
    """
    _testbed_tile(page, name).get_by_role("button", name="Start").click()
    _buffer(page)


@pytest.mark.stateful
def test_t10_two_testbeds_run_simultaneously(dashboard: Page, clean_testbeds):
    page = dashboard

    _reserve_ports(page, ALL_PORTS)

    # Build and Apply both testbeds first — neither is started yet. A
    # generous 15/60/15 = 90s ramp on each gives plenty of overlap margin
    # around the few seconds it takes to Start both back-to-back below.
    _build_and_apply_testbed(
        page,
        name=TESTBED_A_NAME,
        ports=PORTS_A,
        ip_base="10.0.3.",
        cidr="25",
        rate_gbps=1,
        protocol_button_name=None,  # UDP, the default-highlighted protocol
        frame_size=1000,
        ramp=(15, 60, 15),
    )
    _build_and_apply_testbed(
        page,
        name=TESTBED_B_NAME,
        ports=PORTS_B,
        ip_base="10.0.4.",
        cidr="25",
        rate_gbps=1,
        protocol_button_name="TCP",
        frame_size=800,
        ramp=(15, 60, 15),
    )

    # Start both back-to-back, minimizing the gap between them.
    _start_testbed(page, TESTBED_A_NAME)
    _start_testbed(page, TESTBED_B_NAME)

    tile_a = _testbed_tile(page, TESTBED_A_NAME)
    tile_b = _testbed_tile(page, TESTBED_B_NAME)

    # --- The actual concurrency assertion: both are live at the same time ---
    expect(tile_a.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile_b.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    # Re-check A is still live right after confirming B is live, proving
    # both runs genuinely overlap rather than the product silently
    # queueing/serializing them.
    expect(tile_a.get_by_role("button", name="Stop")).to_be_visible()

    # --- Wait for both runs to finish naturally — never race ahead ---
    expect(tile_a.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)
    expect(tile_b.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify both PASS independently, before touching Deactivate/Release ---
    # The result badge displays as "PASS" (CSS text-transform: uppercase)
    # but the underlying DOM text is lowercase "pass".
    # "Reports: N" only appears once the testbed is deactivated (see project
    # bugs memory, 2026-08-28) — both are still active here, so the same
    # run-history page is reached via "Stats" instead.
    tile_a.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    tile_b.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
