"""T9 — Selecting a saved network profile in a new testbed populates its fields.

Confirmed by exploration: picking a saved profile from the wizard step
1's "Network profile" dropdown on a *different, fresh* testbed
auto-enables the USE toggle for each port the profile references and
fills in that port's Line Rate and Peer Port — not just a label change.
"""
import pytest
from playwright.sync_api import Page, expect

SOURCE_TESTBED = "T9-ProfileSource-DeleteMe"
TARGET_TESTBED = "T9-ProfileTarget-DeleteMe"
PROFILE_NAME = "T9-SelectProfile-Profile-DeleteMe"


def _testbed_tile(page: Page, name: str):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_testbed_if_present(page: Page, name: str):
    tile = _testbed_tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_testbed_tile(page, name)).to_have_count(0, timeout=10000)


def _profiles_section(page: Page):
    return page.locator(".card", has=page.get_by_role("heading", name="Network Profiles"))


def _delete_profile_if_present(page: Page, name: str = PROFILE_NAME):
    section = _profiles_section(page)
    row = section.locator("tr", has_text=name)
    if row.count() > 0:
        row.locator('span[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(section.locator("tr", has_text=name)).to_have_count(0, timeout=10000)


def _create_testbed(page: Page, name: str):
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _testbed_tile(page, name)
    expect(tile).to_have_count(1, timeout=10000)
    return tile


def _back_to_dashboard(page: Page):
    page.get_by_role("button", name="← Dashboard").click()
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    if discard_btn.is_visible():
        discard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_testbed_if_present(dashboard, SOURCE_TESTBED)
    _delete_testbed_if_present(dashboard, TARGET_TESTBED)
    _delete_profile_if_present(dashboard)
    yield
    _delete_testbed_if_present(dashboard, SOURCE_TESTBED)
    _delete_testbed_if_present(dashboard, TARGET_TESTBED)
    _delete_profile_if_present(dashboard)


@pytest.mark.hardware_free
def test_t9_selecting_profile_populates_ports(dashboard: Page, clean_up):
    page = dashboard

    # Build the profile from a scratch source testbed.
    _create_testbed(page, SOURCE_TESTBED)
    _testbed_tile(page, SOURCE_TESTBED).get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    page.get_by_role("button", name="Save as a new profile…", exact=True).click()
    expect(page.get_by_text("Save network profile", exact=True)).to_be_visible(timeout=10000)
    page.get_by_placeholder("e.g. Lab-A").fill(PROFILE_NAME)
    page.get_by_role("button", name="Save profile", exact=True).click()
    expect(
        page.locator("select.fc").filter(has=page.locator("option", has_text=PROFILE_NAME))
    ).to_have_count(1, timeout=10000)
    _back_to_dashboard(page)

    # Fresh, unrelated testbed: select the saved profile and check it
    # populates the port config rather than just labeling the dropdown.
    _create_testbed(page, TARGET_TESTBED)
    _testbed_tile(page, TARGET_TESTBED).get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    expect(row1.locator(".toggle input")).not_to_be_checked()

    profile_select = page.locator("select.fc").filter(
        has=page.locator("option", has_text=PROFILE_NAME)
    )
    profile_select.select_option(label=PROFILE_NAME)

    expect(row1.locator(".toggle input")).to_be_checked()
    expect(row2.locator(".toggle input")).to_be_checked()
    expect(row1.locator('input[placeholder="line rate"]')).to_have_value("10")
    expect(row1.locator("select").nth(1)).to_have_value("2")  # peer = Port 2
