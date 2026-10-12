"""T3 — Reserved By / Test Name columns populate correctly while a
testbed is active.

Confirmed by exploration: the dashboard's Port Status table shows
Reserved By "test (you)" for a port reserved directly via its own
Reserve button, but the Test Name column stays "—" for that kind of
plain reservation. Test Name only populates once a testbed is actually
activated.

UI update (2026-09-17): under this account's default "Automatic"
Activation Mode preference (User menu -> Preferences -> Activation Mode),
the old separate Apply ("Save & activate") step no longer exists — a
single "Start" button now activates AND runs traffic together (behind a
"Testbed is Inactive" confirmation modal). So, unlike before, this test
can no longer inspect an activated-but-not-yet-running state: some
traffic now runs briefly as an unavoidable side effect of activating.
That doesn't affect what's actually being asserted here (Reserved By /
Test Name reflect activation, not run state), so the test still doesn't
need to wait for a run to finish — it just can't claim "no traffic is
ever generated" as a resource-usage guarantee like it used to.
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
NAME = "T3-ActiveCols"
assert_activatable_name(NAME)
PORTS = ["Port 1", "Port 2"]


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=NAME)


def _delete_testbed_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        page.wait_for_timeout(400)
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
            expect(row.get_by_text("Unreserved", exact=True)).to_be_visible(timeout=10000)


@pytest.fixture
def clean_testbed(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    yield
    _release_ports(dashboard)
    _delete_testbed_if_present(dashboard)


@pytest.mark.stateful
def test_t3_reserved_by_and_test_name_populate_on_activation(
    dashboard: Page, clean_testbed
):
    page = dashboard

    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Unreserved", exact=True)).to_be_visible()

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _testbed_tile(page)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()

    page.get_by_role("button", name="3 Streams", exact=False).click()
    expect(page.get_by_role("button", name="✚ Add Stream", exact=True)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="✚ Add Stream", exact=True).click()
    expect(page.get_by_role("button", name="Add stream", exact=True)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="Add stream", exact=True).click()

    # Start reserves the ports at the engine and populates Test Name as
    # part of activation — see module docstring re: the merged
    # activate+run "Start" flow this account's Activation Mode uses now.
    page.get_by_role("button", name="Start", exact=True).click()
    continue_btn = page.get_by_role("button", name="Continue", exact=True)
    if continue_btn.is_visible():
        continue_btn.click()
    expect(page.get_by_role("heading", name="Statistics", exact=False)).to_be_visible(
        timeout=75000
    )

    page.get_by_role("button", name="← Dashboard").click()
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    if discard_btn.is_visible():
        discard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)

    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible()
        expect(row).to_contain_text("test (you)")
        # The Test Name column truncates in the DOM itself (not just
        # visually via CSS) at 15 chars — the same backend name limit
        # that 502s activate for longer names, so the slice is a no-op
        # now that NAME is within it, but keeps the guard explicit.
        expect(row).to_contain_text(NAME[:15])
