"""T4 — Create testbed: name + module → card appears, counter increments.

Selector note: the per-card action icons (export/clone/delete) have no
accessible name or data-testid — only a `data-tip` attribute used for the
hover tooltip. `data-tip` is the closest thing to a stable identifier here
and is used for scoping instead of position, but a real data-testid would
be preferable; worth requesting from the frontend team (see T4 plan note).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T4-Create-DeleteMe"


@pytest.mark.hardware_free
def test_t4_create_testbed_adds_card_and_increments_counter(dashboard: Page, clean_up):
    page = dashboard
    before = DashboardPage(page).saved_count()

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()

    tile = DashboardPage(page).testbed_entry(NAME)
    expect(tile).to_have_count(1, timeout=10000)
    expect(tile).to_contain_text("Traffic Engine")
    assert DashboardPage(page).saved_count() == before + 1
