"""T10/T12 combined lifecycle test — ICMP variant.

Sibling of test_t10_t12_lifecycle_udp_1gbps_1500b.py and
test_t10_t12_lifecycle_tcp_2gbps_512b.py with different parameters: ICMP
instead of UDP/TCP, 5 Gbps line rate, 64-byte (minimum Ethernet) frames,
Port 1 + Port 2 instead of Port 3+4 / 5+6, a /26 subnet instead of /25
(62 hosts instead of 126 — the CIDR select only offers /25-/32, so /24
isn't an option) on a distinct IP range, and an 8/45/8 = 61s ramp.

Creates a Traffic Engine testbed on Port 1 + Port 2, configures a single
ICMP stream at 5 Gbps line rate with 64-byte frames, activates it, waits
for the run to finish on its own, and asserts the result is PASS — then
cleans up (release ports, delete testbed).

Stateful: generates real traffic on shared hardware.

Selector note: several wizard controls (frame size input, ramp inputs,
network config fields, the subnet-mask <select>) have no accessible name,
role, or data-testid, so this falls back to CSS position (`.fc`, `.seg`,
`nth-child`) recorded via Playwright codegen. Flagging per the "report UI
issues" convention — these controls, plus testbed tiles (`div.tb-tile`,
no ARIA role at all) and icon-only action buttons (download/duplicate/
delete with no aria-label/title), would benefit from data-testid
attributes; noting here for the PR description rather than silently
working around it.
"""
import pytest
from playwright.sync_api import Page, expect

TESTBED_NAME = "T10-T12-Lifecycle-ICMP-5Gbps-64B"
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
    # time out / crash teardown — seen 2026-08-25 investigating a slow
    # activation whose request was still pending when goto() fired).
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal
        # (Discard / Save & close / Keep editing) that blocks the plain
        # click above from actually landing on the dashboard.
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
def test_t10_t12_lifecycle_icmp_5gbps_64b(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 1 and Port 2 ---
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

    # --- Wizard step 1: Ports — enable Port 1 & Port 2, 5 Gbps line rate ---
    # Always scope Edit to the testbed by name, never by position — a
    # positional index silently edits whichever tile happens to sit there.
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(1) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(2) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=f"{port_label} 10 Gbps ⚠ reserved by"
        ).get_by_placeholder("line rate")
        rate_field.fill("5")
        _buffer(page)
    page.get_by_role(
        "row", name="Port 2 10 Gbps ⚠ reserved by"
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    # Distinct IP range (10.0.2.x) and a /26 mask instead of the siblings'
    # /25, so this exercises a different host-count computation
    # (62 hosts instead of 126 — see T6 in the plan) on top of the
    # different protocol/ports/rate.
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.2.1")
    _buffer(page)
    page.locator(".seg").first.select_option("26")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.2.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("26")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.2.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.2.2")
    _buffer(page)

    # --- Wizard step 3: Streams — ICMP (explicitly selected), 64-byte frames ---
    # ICMP isn't the picker's default-highlighted protocol (UDP is), so it
    # has to be selected explicitly, same as the TCP sibling test.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="ICMP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    # Layer chip's accessible name combines label + tooltip ("ICMP Edit
    # ICMP"), not exact "ICMP" — use a substring role match, mirroring the
    # UDP/TCP siblings. Asserting "at least one" rather than "exactly
    # one" — see UDP sibling test for why (icon-only delete button has no
    # accessible name to target reliably if cleanup to exactly one were
    # ever needed).
    expect(page.get_by_role("button", name="ICMP Edit ICMP").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("64")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
    # 8/45/8 = 61s ramp — distinct from the UDP sibling's 10/50/10 (70s)
    # and the TCP sibling's 5/30/5 (40s).
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
    page.locator(".fc > input").first.fill("8")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("45")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("8")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    # "Apply" ("Save & activate on the unit") swaps the whole edit-view
    # action bar from Delete/Save/Apply to an active-testbed bar with
    # Delete/Deactivate/Stats/Save/Start — this doesn't happen instantly.
    # Wait on "Deactivate" — a real, role-addressable button that only
    # exists in the post-Apply bar — rather than racing ahead. The
    # activate call itself carries a `?wait=15` server-side contract and
    # can legitimately take longer than 30s plus UI lag to resolve —
    # confirmed 2026-08-25 on the UDP sibling test — so give it real room.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()

    # Clicking Start navigates into the Statistics view. A hard page.goto()
    # or go_back() here fails — this app's SPA routing doesn't survive a
    # forced reload/history nav mid-transition into the live-run view. Use
    # the SPA's own "← Dashboard" button instead.
    page.wait_for_timeout(2000)
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
    tile.get_by_role("button", name="Reports:").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
