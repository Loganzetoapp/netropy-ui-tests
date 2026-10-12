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

UI update (2026-09-17): this test used to build+Apply (configure +
activate, no traffic) both testbeds first, waiting at the Deactivate bar,
then Start both back-to-back — that two-step gap was what let both be
staged before either generated traffic, guaranteeing overlap regardless
of how long testbed B took to build. See
test_t10_t12_lifecycle_multistream_udp_tcp_100mbps.py for the full
writeup: Apply and Start have been merged into a single "Start" action
that activates AND starts traffic together, so there is no more way to
stage a testbed at "activated but idle" — clicking Start on testbed A
immediately starts its traffic, before testbed B has even been built.

To keep genuine overlap under this constraint, testbed A is now given a
deliberately long hold phase (15/180/15 = 210s) — comfortably longer than
the ~90s the original sequencing-bug writeup measured for building a
second testbed through the wizard — so A is still guaranteed to be live
when testbed B's own Start (build immediately followed by Start) fires.
B keeps a shorter 15/60/15 = 90s ramp. This is a best-effort adaptation
of the original design's intent (assert genuine concurrent runs, not a
coincidental near-miss) rather than a re-validated timing measurement —
see NEEDS HUMAN REVIEW below.

An earlier version of this test (pre-dating even the Apply/Start merge)
built+started A, then built B while A ran, with too-short a ramp on A;
A's short ramp finished before B's ~90s of wizard setup was even done,
so they never actually overlapped — sequencing bug, not a selector
issue. That same failure mode is exactly what the long A hold above
guards against, now structurally required rather than optional.

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


def _build_and_start_testbed(
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
    """Build a Traffic Engine testbed through the wizard and click Start —
    which now activates AND starts traffic together in one action (see
    module docstring's UI-update note); there is no longer a way to Apply
    a testbed without also starting its traffic. Waits for the live
    Statistics view, then returns to the dashboard. Generalized over
    ports/IP/protocol/frame-size/ramp so it can build+start two different
    testbeds in one test, back-to-back.
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
    # Start activates the testbed AND starts traffic together (after a
    # "Testbed is Inactive" confirmation modal) — see module docstring's
    # UI-update note. This is this testbed's one and only Start click;
    # there's no separate Apply-then-Start pair anymore.
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

    # Landing on the Statistics view navigates away from the dashboard —
    # get back to it so the next testbed's "Create Testbed" button is
    # reachable.
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()


@pytest.mark.stateful
def test_t10_two_testbeds_run_simultaneously(dashboard: Page, clean_testbeds):
    page = dashboard

    _reserve_ports(page, ALL_PORTS)

    # NEEDS HUMAN REVIEW: Start now activates + runs traffic in one action
    # (see module docstring's UI-update note), so testbed A necessarily
    # starts generating traffic here, immediately — well before testbed B
    # even exists — rather than both being staged idle first and Started
    # back-to-back as this test originally did. A's hold phase below
    # (15/180/15 = 210s) is sized to comfortably outlast building +
    # Starting testbed B (measured at ~90s for a full wizard pass in the
    # pre-existing sequencing-bug writeup below), so both should still be
    # confirmed live at the same time — but this specific margin hasn't
    # been re-measured against a live run since the Apply/Start merge;
    # if this test flakes on "tile_a Stop not visible" or the two runs
    # don't actually overlap, widen A's hold further rather than assuming
    # a one-off timing fluke.
    _build_and_start_testbed(
        page,
        name=TESTBED_A_NAME,
        ports=PORTS_A,
        ip_base="10.0.3.",
        cidr="25",
        rate_gbps=1,
        protocol_button_name=None,  # UDP, the default-highlighted protocol
        frame_size=1000,
        ramp=(15, 180, 15),
    )
    _build_and_start_testbed(
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

    tile_a = _testbed_tile(page, TESTBED_A_NAME)
    tile_b = _testbed_tile(page, TESTBED_B_NAME)

    # --- The actual concurrency assertion: both are live at the same time ---
    # A was Started first and should still be well within its long hold
    # phase by now (B's build+Start just happened in between).
    expect(tile_a.get_by_role("button", name="Stop")).to_be_visible()
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
