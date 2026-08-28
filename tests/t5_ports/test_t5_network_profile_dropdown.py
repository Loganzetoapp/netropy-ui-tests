"""T5 — Network profile dropdown default state and "Save as a new profile…".

A fresh draft testbed has no saved network profiles to select, so the
dropdown offers only "— Manual configuration —" (value=""). The "Save as
a new profile…" button (a real `<button>`, not a select option) only
appears once at least one port is enabled — with zero ports enabled it
isn't rendered at all, confirmed by exploration. Actually saving/
selecting a profile is T9's job (network profiles) — this just confirms
the step 1 default state and that the entry point exists once there's
something to save.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-NetworkProfile-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _cleanup_from_wherever(page: Page, name: str = NAME):
    if _tile(page, name).count() > 0:
        _delete_if_present(page, name)
        return
    delete_btn = page.get_by_role("button", name="Delete", exact=True)
    if delete_btn.count() > 0 and delete_btn.first.is_visible():
        delete_btn.first.click()
        page.locator("button.btn-danger", has_text="Delete").click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    _delete_if_present(page, name)


def _create_and_open_edit(page: Page, name: str = NAME):
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _tile(page, name)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t5_network_profile_dropdown_default_state(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

    profile_select = page.locator("text=Network profile").locator(
        "xpath=following::select[1]"
    )
    expect(profile_select).to_have_value("")
    assert profile_select.locator("option").all_inner_texts() == [
        "— Manual configuration —"
    ]

    # The "Save as a new profile…" entry point only appears once there's
    # at least one enabled port to save a config for.
    save_as_profile_btn = page.get_by_role("button", name="Save as a new profile…")
    expect(save_as_profile_btn).to_have_count(0)

    page.locator("tr").nth(1).locator(".toggle .track").click()
    expect(save_as_profile_btn).to_be_visible()
