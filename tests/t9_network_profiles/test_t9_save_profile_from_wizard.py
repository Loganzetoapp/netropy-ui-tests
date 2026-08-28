"""T9 — Save current port config as a network profile from the wizard.

Confirmed by exploration: the wizard step 1's "Save as a new profile…"
button opens a "Save network profile" modal (Profile name field,
placeholder "e.g. Lab-A · 2x10G"). Saving adds the profile to that
wizard's own "Network profile" dropdown immediately, and — since network
profiles are a dashboard-global list, not scoped to one testbed or user
— it also appears in the dashboard's Network Profiles card/table for
everyone, the same way testbeds do. Cleanup deletes only this test's own
uniquely-named profile from that global list, exactly as the testbed
tests only ever touch their own uniquely-named testbed.
"""
import pytest
from playwright.sync_api import Page, expect

TESTBED_NAME = "T9-SaveProfile-DeleteMe"
PROFILE_NAME = "T9-SaveProfile-Profile-DeleteMe"


def _testbed_tile(page: Page, name: str = TESTBED_NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_testbed_if_present(page: Page, name: str = TESTBED_NAME):
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


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    _delete_profile_if_present(dashboard)
    yield
    _delete_testbed_if_present(dashboard)
    _delete_profile_if_present(dashboard)


@pytest.mark.hardware_free
def test_t9_save_profile_from_wizard_appears_everywhere(dashboard: Page, clean_up):
    page = dashboard
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(TESTBED_NAME)
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

    page.get_by_role("button", name="Save as a new profile…", exact=True).click()
    expect(page.get_by_text("Save network profile", exact=True)).to_be_visible(timeout=10000)
    page.get_by_placeholder("e.g. Lab-A").fill(PROFILE_NAME)
    page.get_by_role("button", name="Save profile", exact=True).click()

    profile_select = page.locator("select.fc").filter(
        has=page.locator("option", has_text=PROFILE_NAME)
    )
    expect(profile_select).to_have_count(1, timeout=10000)

    # Network Profiles only renders on the dashboard, not inside the
    # wizard — navigate back to see it there too.
    page.get_by_role("button", name="← Dashboard").click()
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    if discard_btn.is_visible():
        discard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)

    section = _profiles_section(page)
    profile_row = section.locator("tr", has_text=PROFILE_NAME)
    expect(profile_row).to_have_count(1, timeout=10000)
    expect(profile_row.locator(".np-d7-pcount")).to_have_text("2")
    expect(profile_row.locator(".np-d7-topo-min")).to_have_text("P1 ⇄ P2")
