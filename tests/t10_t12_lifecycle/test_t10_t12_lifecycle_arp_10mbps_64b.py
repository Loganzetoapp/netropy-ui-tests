"""T10/T12 combined lifecycle test — ARP variant.

Sibling of the UDP/TCP/ICMP lifecycle tests, using a Layer 2 protocol
instead of anything IP-based — the first lifecycle test in this suite
that isn't UDP/TCP/ICMP-shaped.

Protocol research (via the live "✚ Add Stream" picker before writing this
test — see project_bugs_found memory, 2026-09-10): ARP's picker entry
reads "Address resolution frames", layer stack **Ethernet → Payload only**
— no IPv4/UDP/TCP layer at all, and no "Default ports" line (there's
nothing to have a port). Creates exactly one stream ("arp") per Add,
same 1-stream shape as every other single-protocol sibling.

**Network Configuration deliberately left at its auto-filled defaults**
here, unlike every IP-based sibling which sets custom static IPs: since
ARP has no IP layer, per-port source/destination IP addressing isn't
meaningful for what the stream actually sends on the wire. Confirmed by
exploration that the wizard's step 2 still renders the full IP/MAC form
regardless of protocol (it's generic to the testbed, not stream-aware),
so this is a deliberate choice to leave it alone, not an oversight.

Frame size is pinned to 64 bytes, the Ethernet minimum, matching a real
(non-padded) ARP frame's actual size on the wire more closely than a
larger value would. Line rate is a modest 10 Mbps — real ARP traffic is
inherently bursty address-resolution lookups, not sustained bulk load,
so this is the lowest rate among this suite's lifecycle siblings.

Creates a Traffic Engine testbed on Port 3 + Port 4, configures a single
ARP stream, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

Port note (2026-09-10): originally written against Port 5+6, and passed
cleanly there once — but 5/6 went Down/No Link again right after (the
same recurring hardware issue documented in project_bugs_found memory,
not caused by this test), so this was switched to Port 3+4 to keep the
suite immediately runnable. Switch back once 5/6 are confirmed healthy
again, if a fully disjoint port set becomes preferable.

Stateful: generates real traffic on the box.

Selector note: same caveats as every sibling — several wizard controls
have no accessible name/role/data-testid and fall back to CSS position
(`.fc`, `.seg`, `nth-child`).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-Life-ARP"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
# This app's own UI needs a short settling moment after several wizard
# actions (toggles, selects) or the next locator's actionability wait can
# time out — see feedback_codegen_replay_reliability memory. expect()
# assertions are used for the actual correctness checks; this is purely a
# settle buffer.
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
def test_t10_t12_lifecycle_arp_10mbps_64b(dashboard: Page, clean_testbed):
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

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 10 Mbps line rate ---
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        row = page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label)}\b"))
        # Switch unit to Mbps before filling — 3rd <select> in the row
        # (Direction, Peer port, Unit); pattern confirmed in
        # test_t5_line_rate_unit_conversion.py. Real ARP traffic is
        # bursty address-resolution lookups, not sustained bulk load.
        row.locator("select").nth(2).select_option(label="Mbps")
        _buffer(page)
        rate_field = row.get_by_placeholder("line rate")
        rate_field.fill("10")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 4\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration — deliberately skipped.
    # ARP has no IP layer (see module docstring); the auto-filled defaults
    # the wizard applies regardless of protocol are left untouched.

    # --- Wizard step 3: Streams — ARP, 64-byte (Ethernet minimum) frames ---
    # ARP isn't the picker's default-highlighted protocol (UDP is), so it
    # has to be selected explicitly, same as every non-UDP sibling.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="ARP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    expect(page.get_by_role("button", name="Ethernet Edit Ethernet").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("64")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
    # 3/15/3 = 21s ramp — the shortest in this suite, matching ARP's
    # naturally brief, bursty real-world traffic pattern.
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
    page.locator("div:nth-child(2) > .fc > input").fill("15")
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

    # --- Wait for the run to finish naturally — never race ahead of it ---
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify PASS before touching Deactivate/Release ---
    # "Reports: N" only appears once the testbed is deactivated (see project
    # bugs memory, 2026-08-28) — at this point it's still active, so the
    # same run-history page is reached via "Stats" instead.
    tile.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
