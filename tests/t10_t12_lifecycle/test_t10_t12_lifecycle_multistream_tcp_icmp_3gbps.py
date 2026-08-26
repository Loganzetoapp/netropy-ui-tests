"""T10/T12 combined lifecycle test — multi-stream (TCP + ICMP), no UDP.

Sibling of the single-stream UDP/TCP/ICMP lifecycle tests, but exercises
a wizard path none of them cover: a testbed with *two streams on one
testbed* (TCP + ICMP together), rather than one stream per testbed.
Deliberately excludes UDP — every other lifecycle test in this suite
already uses it as its sole stream, so this one specifically covers the
"multiple non-UDP protocols coexisting" combination.

Creates a Traffic Engine testbed on Port 3 + Port 4, adds a TCP stream
(900-byte frames) and an ICMP stream (100-byte frames) to the same
testbed, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

Stateful: generates real traffic on shared hardware.

Port note (2026-08-26): Port 3+4 are reused here (already exercised by
the single-stream UDP sibling) because Port 5-8 are all currently
Down/No Link — see project_bugs_found memory. Switch back to an unused
pair once those recover, if a fully disjoint set becomes preferable.

Selector note: same caveats as the single-stream siblings — several
wizard controls have no accessible name/role/data-testid and fall back
to CSS position (`.fc`, `.seg`, `nth-child`). The frame-size input is
additionally indexed per stream row here (`.nth(i)` instead of
`.first`), since with two streams there are two such inputs on the page.
"""
import pytest
from playwright.sync_api import Page, expect

TESTBED_NAME = "T10-T12-Lifecycle-MultiStream-TCP-ICMP-3Gbps"
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
def test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps(dashboard: Page, clean_testbed):
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

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 3 Gbps line rate ---
    # Always scope Edit to the testbed by name, never by position — a
    # positional index silently edits whichever tile happens to sit there.
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
        rate_field.fill("3")
        _buffer(page)
    page.get_by_role(
        "row", name="Port 4 10 Gbps ⚠ reserved by"
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.6.1")
    _buffer(page)
    page.locator(".seg").first.select_option("27")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.6.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("27")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.6.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.6.2")
    _buffer(page)

    # --- Wizard step 3: Streams — TCP + ICMP, two streams on one testbed ---
    # Neither is the picker's default-highlighted protocol (UDP is), so
    # both have to be selected explicitly, same as the single-stream TCP
    # and ICMP siblings.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)

    # Stream 1: TCP, 900-byte frames.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="TCP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    # Layer chip's accessible name combines label + tooltip ("TCP Edit
    # TCP"), not exact "TCP" — use a substring role match.
    expect(page.get_by_role("button", name="TCP Edit TCP").first).to_be_visible()
    # Only one stream row exists at this point, so .first unambiguously
    # targets it.
    page.locator("td:nth-child(5) > .fc").first.fill("900")
    _buffer(page)
    page.locator("td:nth-child(5) > .fc").first.press("Enter")
    _buffer(page)

    # Stream 2: ICMP, 100-byte frames — added on top of the TCP stream
    # above, not replacing it.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="ICMP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="ICMP Edit ICMP").first).to_be_visible()
    # Two stream rows exist now (TCP added first, ICMP appended below) —
    # index explicitly rather than .first/.last to avoid ambiguity.
    frame_size_inputs = page.locator("td:nth-child(5) > .fc")
    expect(frame_size_inputs).to_have_count(2)
    frame_size_inputs.nth(1).fill("100")
    _buffer(page)
    frame_size_inputs.nth(1).press("Enter")
    _buffer(page)

    # Both streams still present after the second Add Stream — confirms
    # adding stream 2 didn't silently replace stream 1.
    expect(page.get_by_role("button", name="TCP Edit TCP").first).to_be_visible()
    expect(page.get_by_role("button", name="ICMP Edit ICMP").first).to_be_visible()

    # --- Wizard step 4: Traffic and Load Profile ---
    # 5/25/5 = 35s ramp — distinct from the single-stream siblings'
    # 10/50/10, 5/30/5, and 8/45/8.
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
    page.locator("div:nth-child(2) > .fc > input").fill("25")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("5")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    # "Apply" ("Save & activate on the unit") swaps the whole edit-view
    # action bar from Delete/Save/Apply to an active-testbed bar with
    # Delete/Deactivate/Stats/Save/Start — this doesn't happen instantly.
    # The activate call itself carries a `?wait=15` server-side contract
    # and can legitimately take longer than 30s plus UI lag to resolve —
    # confirmed 2026-08-25 on the UDP sibling test — so give it real room.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()

    # Clicking Start (from inside the wizard's post-Apply action bar)
    # navigates into the Statistics view. A hard page.goto() or go_back()
    # here fails — this app's SPA routing doesn't survive a forced
    # reload/history nav mid-transition into the live-run view. Use the
    # SPA's own "← Dashboard" button instead.
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
