"""T9 — Export a network profile, delete it, import it back.

Confirmed by exploration: unlike testbed export (T4), profile export has
no confirm dialog — clicking the card icon downloads immediately.
Filename/body: `network-profiles.json`, `{"format":
"tgen-network-profile", "version": 1, "profiles": [...]}`. The Import
button on the Network Profiles card feeds a hidden
`<input type="file" accept=".json,application/json,.netprofile.json">`.

Not automated here (deliberately, see project memory): the empty-state
text and "Export all with zero profiles" behavior, because the Network
Profiles list is dashboard-global across all users on this shared box —
unlike testbeds, there's no way to scope an "is it empty" or "export
everything" assertion to just this test's own data without either
depending on incidental global state or deleting other people's saved
profiles. Also not automated: a profile referencing a port reserved
elsewhere, since reproducing that needs a real `stateful` port
reservation, which this suite doesn't do without being explicitly asked.
"""
import json

import pytest
from playwright.sync_api import Page, expect

TESTBED_NAME = "T9-ExportImport-DeleteMe"
PROFILE_NAME = "T9-ExportImport-Profile-DeleteMe"


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


def _profile_row(page: Page, name: str = PROFILE_NAME):
    return _profiles_section(page).locator("tr", has_text=name)


def _delete_profile_if_present(page: Page, name: str = PROFILE_NAME):
    row = _profile_row(page, name)
    if row.count() > 0:
        row.locator('span[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_profile_row(page, name)).to_have_count(0, timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    _delete_profile_if_present(dashboard)
    yield
    _delete_testbed_if_present(dashboard)
    _delete_profile_if_present(dashboard)


@pytest.mark.hardware_free
def test_t9_export_then_import_recreates_profile(dashboard: Page, clean_up, tmp_path):
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
    expect(
        page.locator("select.fc").filter(has=page.locator("option", has_text=PROFILE_NAME))
    ).to_have_count(1, timeout=10000)

    page.get_by_role("button", name="← Dashboard").click()
    discard_btn = page.get_by_role("button", name="Discard", exact=True)
    if discard_btn.is_visible():
        discard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)

    row = _profile_row(page)
    expect(row).to_have_count(1, timeout=10000)
    with page.expect_download(timeout=10000) as download_info:
        row.locator('span[data-tip="Export profile JSON"] button').click()
    download = download_info.value
    export_path = tmp_path / download.suggested_filename
    download.save_as(str(export_path))
    exported = json.loads(export_path.read_text())
    assert exported["format"] == "tgen-network-profile"
    assert [p["name"] for p in exported["profiles"]] == [PROFILE_NAME]

    _delete_profile_if_present(page)
    expect(row).to_have_count(0)

    import_input = _profiles_section(page).locator('input[type="file"]')
    import_input.set_input_files(str(export_path))
    expect(row).to_have_count(1, timeout=10000)
    expect(row.locator(".np-d7-pcount")).to_have_text("2")
