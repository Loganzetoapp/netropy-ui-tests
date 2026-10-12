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

from pages import DashboardPage

NAME = "T5-NetworkProfile-DeleteMe"


@pytest.mark.hardware_free
def test_t5_network_profile_dropdown_default_state(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

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
