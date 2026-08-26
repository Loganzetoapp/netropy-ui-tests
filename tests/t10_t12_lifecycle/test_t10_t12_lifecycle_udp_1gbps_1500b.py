"""T10/T12 combined lifecycle test.

Creates a Traffic Engine testbed on Port 3 + Port 4, configures a single
UDP stream at 1 Gbps line rate with 1500-byte frames, activates it, waits
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

TESTBED_NAME = "T10-T12-Lifecycle-UDP-1Gbps-1500B"
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
def test_t10_t12_lifecycle_udp_1gbps_1500b(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 3 and Port 4 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Create testbed ---
    # BUG FOUND 2026-08-25: the product added a collapsible section header
    # (div role="button", aria-expanded, class "hdr-toggle") around the
    # Testbeds section at some point since this test was last run. Its
    # accessible name concatenates the whole section's text, so a
    # non-exact match on "✚ Create Testbed" now also matches that header
    # (strict-mode violation, 2 elements). Use exact=True to get just the
    # real button.
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 1 Gbps line rate ---
    # BUG FOUND (2026-08-20): using a positional index here
    # (`get_by_role("button", name="Edit").nth(2)`, matching the original
    # codegen recording) silently edited the WRONG testbed once a 4th
    # testbed existed on the dashboard — it opened whatever tile happened
    # to sit at index 2, not the one just created. This caused a long,
    # confusing chain of apparent "product flakiness" (phantom pre-existing
    # streams, PUT/activate calls hitting a stale testbed's URL, activation
    # 400s) that was actually this test silently corrupting an unrelated
    # testbed each run. Always target the tile by name instead.
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
        rate_field.fill("1")
        _buffer(page)
    page.get_by_role(
        "row", name="Port 4 10 Gbps ⚠ reserved by"
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.0.1")
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.0.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.0.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.0.2")
    _buffer(page)

    # --- Wizard step 3: Streams — UDP (default-highlighted protocol), 1500-byte frames ---
    # Note: earlier runs of this test appeared to show duplicate/phantom
    # streams here. That turned out to be a downstream symptom of the
    # Edit.nth(2) bug above (each failed attempt was piling more streams
    # onto the same stale, wrong testbed) — not a real product issue.
    # Asserting "at least one UDP stream is present" rather than "exactly
    # one" regardless, since the delete-icon button has no accessible name
    # to reliably target for cleanup (icon-only, no aria-label/title —
    # worth a data-testid, see netropy-ui-reference.md).
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    # Layer chip's accessible name combines label + tooltip ("UDP Edit
    # UDP"), not exact "UDP" — use a substring role match.
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("1500")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
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
    page.locator(".fc > input").first.fill("10")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("50")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("10")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    # "Apply" ("Save & activate on the unit") swaps the whole edit-view
    # action bar from Delete/Save/Apply to an active-testbed bar with
    # Delete/Deactivate/Stats/Save/Start — this doesn't happen instantly.
    # The original codegen recording's fragile concatenated-text click
    # (get_by_text("DeleteDeactivateStatsSaveStart")) worked only because
    # get_by_text() itself waits (up to 30s) for that exact text to exist,
    # which incidentally waited out this transition; it wasn't clicking
    # anything functionally meaningful. Wait on "Deactivate" instead — a
    # real, role-addressable button that only exists in the post-Apply bar.
    # The activate call itself carries a `?wait=15` server-side contract
    # and can legitimately take longer than that plus UI lag to resolve —
    # confirmed 2026-08-25: a run that looked "hung" past 30s later turned
    # out to have actually succeeded, just slower than we'd waited. Give
    # it real room rather than treating slow-but-working as a failure.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()

    # Clicking Start navigates into the Statistics view. A hard page.goto()
    # or go_back() here failed repeatedly with a 30s timeout — this app's
    # SPA routing doesn't survive a forced reload/history nav mid-transition
    # into the live-run view. Use the SPA's own "← Dashboard" button instead.
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Wait for the run to finish naturally — never race ahead of it ---
    # BUG FOUND: checking "Stop has count 0" immediately after Start is a
    # race — if the button hasn't rendered yet, the check passes vacuously
    # (confirmed: a run finished in 85s total including all wizard setup,
    # far less than the 70s ramp alone allows). Confirm Stop actually
    # appears (traffic really started) before waiting for it to go away
    # again (traffic really finished).
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify PASS before touching Deactivate/Release ---
    # The result badge displays as "PASS" (CSS text-transform: uppercase)
    # but the underlying DOM text is lowercase "pass" — exact match on the
    # visually-uppercase string never matches. Confirmed via a11y dump:
    # row "#1latest ... 0.000 % pass ...".
    tile.get_by_role("button", name="Reports:").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
