"""T10 — FAIL path: genuine overload (max rate, min frame size) should
report FAIL.

Every other lifecycle test in this suite only proves the PASS path
works. None of them verify the product correctly detects and reports a
failure — a test suite that's never seen a real failure can't tell you
the failure-detection logic actually works.

Two earlier approaches were tried and ruled out (2026-08-27), both on
the assumption that a routing/addressing misconfiguration between
directly-cabled Port 3 and Port 4 would break delivery:
  1. Wrong Destination IP on both ports — still PASSed at 0.000% loss,
     1.673 Gbps Tx and Rx both.
  2. Wrong Destination MAC on both ports (the actual field a receiving
     NIC has to match) — still PASSed at 0.000% loss, 1.672 Gbps Tx and
     Rx both.
Both are real product-behavior findings, not test bugs: Rx counting
between two directly-cabled ports on this box appears to not be gated
by address-matching at all — it looks like whatever physically arrives
on the wire gets counted, regardless of whether the frame's L2/L3
addressing was "correct" for that receiver. Address-based
misconfiguration doesn't produce a FAIL on this box/topology.

This version tries a different kind of break entirely: genuine
overload. Both ports pushed to 10 Gbps (the max line rate the wizard
allows) with 64-byte frames (minimum Ethernet frame size = maximum
possible packets-per-second for a given bit rate) — the idea being that
if the appliance's own hardware/CPU can't actually sustain max PPS in
both directions at once, real frames get dropped for a real reason,
independent of any address configuration. This is actual hardware
stress, not a config trick, and unlike the address-based attempts it
carries some real risk (accepted deliberately here) of provoking
something like the Port 5-8 link-down issue seen elsewhere in this
suite — if a port drops link during this test, stop and treat it as a
hardware finding, don't retry blindly.

Everything else (Port 3+4, UDP, correct source/destination IPs and
MACs, correct subnet) matches the known-good sibling tests exactly, so
line rate and frame size are the only two variables changed from a
known-PASS config.

Stateful: generates real traffic on shared hardware, at the maximum
rate/PPS this wizard allows.

Selector note: same caveats as the other lifecycle tests — several
wizard controls have no accessible name/role/data-testid and fall back
to CSS position (`.fc`, `.seg`, `nth-child`).
"""
import pytest
from playwright.sync_api import Page, expect

TESTBED_NAME = "T10-FailPath-Overload-10Gbps-64B"
PORTS = ["Port 3", "Port 4"]
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
@pytest.mark.xfail(
    reason=(
        "Confirmed 2026-08-27: this box/topology (Port 3+4, directly "
        "cabled) doesn't produce a FAIL result via any of 3 tried "
        "mechanisms — wrong dest IP, wrong dest MAC, and this test's own "
        "max-rate/min-frame overload all still PASS at 0.000% loss. "
        "Kept as documentation of that finding, not a blocking failure. "
        "If the product/box changes such that this legitimately starts "
        "reporting FAIL, this will XPASS (not an error, strict=False) — "
        "worth noticing and updating this marker/reason at that point."
    ),
    strict=False,
)
def test_t10_fail_path_overload_max_rate_min_frame_reports_fail(dashboard: Page, clean_testbed):
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

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 10 Gbps (max) line rate ---
    # Always scope Edit to the testbed by name, never by position.
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=f"{port_label} 10 Gbps ⚠ reserved by"
        ).get_by_placeholder("line rate")
        rate_field.fill("10")
        _buffer(page)
    page.get_by_role(
        "row", name="Port 4 10 Gbps ⚠ reserved by"
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration — kept correct on purpose ---
    # Two prior versions of this test proved address misconfiguration
    # (wrong Dest IP, then wrong Dest MAC) has zero effect on delivery
    # here — so this version leaves everything address-related correct,
    # letting the auto-fill/auto-link behavior do its normal thing, and
    # relies purely on line rate + frame size (below) to create the
    # actual overload.
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

    # --- Wizard step 3: Streams — UDP (default-highlighted), 64-byte (minimum) frames ---
    # Minimum Ethernet frame size at maximum line rate maximizes
    # packets-per-second — the actual overload variable.
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
    frame_size.fill("64")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile — fast ramp to sustained max rate ---
    # 2/20/2 = 24s: reach full rate almost immediately and hold there,
    # rather than spending most of the run gradually ramping up.
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("2")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("20")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("2")
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

    # --- Verify FAIL, not PASS ---
    # Mirrors the PASS check in the other lifecycle tests: the badge
    # displays uppercase via CSS but the underlying DOM text is
    # lowercase, so match lowercase "fail" exactly. If this still shows
    # "pass", that's another real product finding (the box genuinely
    # sustains 10Gbps/64B without loss) — report it, don't force it.
    tile.get_by_role("button", name="Reports:").click()
    expect(page.get_by_text("fail", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
