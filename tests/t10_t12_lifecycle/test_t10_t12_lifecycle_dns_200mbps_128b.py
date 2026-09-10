"""T10/T12 combined lifecycle test — DNS variant.

Sibling of the UDP/TCP/ICMP lifecycle tests, using a protocol from the
wizard's "Application" category instead of the generic IPv4 ones.

Protocol research (via the live "✚ Add Stream" picker before writing this
test — see project_bugs_found memory, 2026-09-10): DNS's picker entry
reads "Name lookups, UDP port 53", layer stack Ethernet → IPv4 → UDP →
Payload, "Default ports: 2048 → 53", and creates exactly one stream
("dns") per Add — same 1-stream-per-testbed shape as every other
single-protocol lifecycle sibling, just with the destination port
pre-set to 53 instead of UDP's generic 2048. No extra per-stream port
editing needed after picking the protocol.

Confirmed live (not just from the picker's description) that DNS isn't
its own layer: the created stream's layer chips read Ethernet/IPv4/UDP/
Payload, same as the plain UDP sibling — there's no separate "DNS" chip
to wait on, only "UDP".

Line rate/frame size are deliberately realistic for the protocol rather
than reusing the siblings' multi-gigabit values: real DNS traffic is
small queries/responses, not sustained bulk transfer, so this uses 200
Mbps (switching the line-rate unit dropdown, not a fractional Gbps
value) and 128-byte frames (a typical query/response with EDNS
overhead — bigger than a bare 12-byte DNS header, far short of a full
1500-byte frame).

Creates a Traffic Engine testbed on Port 1 + Port 2, configures a single
DNS stream, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

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
TESTBED_NAME = "T10-Life-DNS"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]
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
        # Icon order confirmed via screenshot: [0]=download [1]=duplicate [2]=delete
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    # The test may fail mid-wizard/mid-activation, off the dashboard
    # entirely — get back to it first so the port rows below actually
    # exist. Prefer the SPA's own "← Dashboard" button when it's present
    # (a hard goto() right after an in-flight activate call can itself
    # time out / crash teardown).
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
def test_t10_t12_lifecycle_dns_200mbps_128b(dashboard: Page, clean_testbed):
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

    # --- Wizard step 1: Ports — enable Port 1 & Port 2, 200 Mbps line rate ---
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(1) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(2) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        row = page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label)}\b"))
        # Switch the unit dropdown to Mbps before filling — it's the 3rd
        # <select> in the row (Direction, Peer port, Unit); confirmed
        # pattern from test_t5_line_rate_unit_conversion.py. Real DNS
        # traffic is nowhere near line-rate Gbps, so this uses a realistic
        # 200 Mbps instead of a fractional Gbps value.
        row.locator("select").nth(2).select_option(label="Mbps")
        _buffer(page)
        rate_field = row.get_by_placeholder("line rate")
        rate_field.fill("200")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 2\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.7.1")
    _buffer(page)
    page.locator(".seg").first.select_option("28")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.7.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("28")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.7.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.7.2")
    _buffer(page)

    # --- Wizard step 3: Streams — DNS, 128-byte frames ---
    # DNS isn't the picker's default-highlighted protocol (UDP is), so it
    # has to be selected explicitly, same as every non-UDP sibling.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="DNS", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    # DNS isn't its own layer — the picker's "Layer stack" for it is
    # Ethernet -> IPv4 -> UDP -> Payload (just UDP with dest port 53
    # preset), confirmed live: the stream row's chips read UDP, not DNS.
    # Wait on the UDP chip rather than a "DNS" one that doesn't exist.
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("128")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
    # 6/35/6 = 47s ramp — distinct from every other sibling's ramp.
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("6")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("35")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("6")
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
