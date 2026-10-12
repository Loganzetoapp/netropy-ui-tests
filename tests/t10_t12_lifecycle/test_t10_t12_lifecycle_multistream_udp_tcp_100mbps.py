"""T10/T12 combined lifecycle test — multi-stream (UDP + TCP), 100 Mbps.

Sibling of the multistream TCP+ICMP lifecycle test, but at Mbps-scale line
rate rather than Gbps, and with UDP in place of ICMP as the second stream.

Creates a Traffic Engine testbed on Port 3 + Port 4, sets each port's line
rate to 100 Mbps, adds a UDP stream (1500-byte frames) and a TCP stream
(512-byte frames) to the same testbed, activates it, waits for the run to
finish on its own, and asserts the result is PASS — then cleans up
(release ports, delete testbed).

Stateful: generates real traffic on shared hardware.

Selector note: same caveats as the other lifecycle siblings — several
wizard controls have no accessible name/role/data-testid and fall back to
CSS position (`.fc`, `.seg`, `nth-child`). The frame-size input is
additionally indexed per stream row here (`.nth(i)` instead of `.first`),
since with two streams there are two such inputs on the page. The line
rate unit `<select>` is the 3rd `<select>` in a port row (after DIRECTION
and PEER PORT) — confirmed via test_t5_line_rate_unit_conversion.py.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-Life-UT100"
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
def test_t10_t12_lifecycle_multistream_udp_tcp_100mbps(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 3 and Port 4 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Create testbed ---
    # The Testbeds section has a collapsible header whose accessible name
    # concatenates the whole section's text, so a non-exact match on
    # "✚ Create Testbed" hits a strict-mode violation (2 elements) —
    # exact=True gets just the real button.
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 100 Mbps line rate ---
    # Always scope Edit to the testbed by name, never by position — a
    # positional index silently edits whichever tile happens to sit there.
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        # Anchor on the port label at the start of the row's accessible
        # name rather than the old "{port} 10 Gbps ⚠ reserved by" literal
        # — a "UNIT" column (value "Local") was added between the port
        # name and the rate, breaking the contiguous substring match. A
        # start-anchor also disambiguates from other ports' rows, which
        # list this port as a Peer Port dropdown option elsewhere in
        # their own row text.
        row = page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label)}\b"))
        # Switch the unit to Mbps *before* filling the rate — the unit
        # select converts whatever value is already in the field (see
        # test_t5_line_rate_unit_conversion.py: 10 Gbps -> switch to Mbps
        # -> field becomes 10000), so switching first avoids having to
        # fill the Gbps-scaled equivalent.
        unit_select = row.locator("select").nth(2)
        unit_select.select_option(label="Mbps")
        _buffer(page)
        rate_field = row.get_by_placeholder("line rate")
        rate_field.fill("100")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 4\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.8.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.8.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.8.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.8.2")
    _buffer(page)

    # --- Wizard step 3: Streams — UDP + TCP, two streams on one testbed ---
    # UDP is the picker's default-highlighted protocol, so it needs no
    # explicit click; TCP does.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)

    # Stream 1: UDP, 1500-byte frames.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    # Layer chip's accessible name combines label + tooltip ("UDP Edit
    # UDP"), not exact "UDP" — use a substring role match.
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    # Only one stream row exists at this point, so .first unambiguously
    # targets it.
    page.locator("td:nth-child(5) > .fc").first.fill("1500")
    _buffer(page)
    page.locator("td:nth-child(5) > .fc").first.press("Enter")
    _buffer(page)

    # Stream 2: TCP, 512-byte frames — added on top of the UDP stream
    # above, not replacing it.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="TCP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="TCP Edit TCP").first).to_be_visible()
    # Two stream rows exist now (UDP added first, TCP appended below) —
    # index explicitly rather than .first/.last to avoid ambiguity.
    frame_size_inputs = page.locator("td:nth-child(5) > .fc")
    expect(frame_size_inputs).to_have_count(2)
    frame_size_inputs.nth(1).fill("512")
    _buffer(page)
    frame_size_inputs.nth(1).press("Enter")
    _buffer(page)

    # Both streams still present after the second Add Stream — confirms
    # adding stream 2 didn't silently replace stream 1.
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    expect(page.get_by_role("button", name="TCP Edit TCP").first).to_be_visible()

    # --- Wizard step 4: Traffic and Load Profile ---
    # 5/20/5 = 30s ramp — distinct from the other lifecycle siblings'
    # 10/50/10, 5/30/5, 8/45/8, and 5/25/5.
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
    page.locator(".fc > input").first.fill("5")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("20")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("5")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    # BUG FOUND (2026-09-17): every other lifecycle test in this suite
    # clicks a button named "Apply" here ("Save & activate on the unit",
    # per netropy-ui-reference.md's description of the edit view's bottom
    # bar), then a separate "Start" once the bar swaps to an
    # active-testbed layout. That flow no longer exists for a
    # freshly-created draft testbed — confirmed by re-running an existing
    # passing sibling (test_t10_t12_lifecycle_udp_1gbps_1500b.py), which
    # now fails identically waiting on "Apply". The bottom bar for a draft
    # currently reads Discard Changes / Delete / Save / Start
    # (screenshot-verified) — Save-and-activate and Start-traffic have
    # been merged into one "Start" action. Clicking it pops a "Testbed is
    # Inactive" confirmation modal ("Start will activate ... then run
    # traffic" — also offers a "Don't show this again" checkbox and a tip
    # about a separate-Activate-step preference), which needs its own
    # "Continue" click; after that it goes straight to the live
    # Statistics view with traffic already running (no intermediate
    # "Deactivate" state to wait on, and no second "Start" to click). This
    # is a product UI/workflow change affecting the whole suite, not
    # something specific to this test — flagged for the PR description
    # rather than silently reusing the stale two-step selectors.
    page.get_by_role("button", name="Start", exact=True).click()
    _buffer(page)
    continue_btn = page.get_by_role("button", name="Continue", exact=True)
    if continue_btn.is_visible():
        continue_btn.click()

    # Activation + traffic start together carry the same `?wait=15`
    # server-side contract the old two-step flow did, so give it the same
    # real room rather than treating slow-but-working as a failure.
    expect(page.get_by_role("heading", name="Statistics", exact=False)).to_be_visible(
        timeout=75000
    )
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Wait for the run to finish naturally — never race ahead of it ---
    # Confirm Stop actually appears (traffic really started) before waiting
    # for it to go away again (traffic really finished) — checking "Stop
    # has count 0" immediately after Start is a race that can pass
    # vacuously if the button hasn't rendered yet.
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify PASS before touching Deactivate/Release ---
    # The result badge displays as "PASS" (CSS text-transform: uppercase)
    # but the underlying DOM text is lowercase "pass".
    # "Reports: N" only appears once the testbed is deactivated (see project
    # bugs memory, 2026-08-28) — at this point it's still active, so the
    # same run-history page is reached via "Stats" instead.
    tile.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
