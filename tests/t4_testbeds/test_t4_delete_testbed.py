"""T4 — Delete a testbed, both from the card icon and from inside Edit.

Both paths funnel through the same confirm dialog
(`get_by_role("button", name="Delete", exact=True)`). The Edit-view
action bar exposes its own Delete/Save/Apply buttons — confirmed by
exploration; see Edit-view action-bar notes in
test_t10_t12_lifecycle_icmp_5gbps_64b.py for how that bar changes once
a testbed is activated (not relevant here, this testbed never activates).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T4-Delete-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _create(page: Page, name: str = NAME):
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    expect(_tile(page, name)).to_have_count(1, timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_if_present(dashboard)
    yield
    _delete_if_present(dashboard)


@pytest.mark.hardware_free
def test_t4_delete_from_card_removes_tile(dashboard: Page, clean_up):
    page = dashboard
    _create(page)

    tile = _tile(page)
    tile.locator('[data-tip="Delete"] button').click()
    page.get_by_role("button", name="Delete", exact=True).click()
    expect(tile).to_have_count(0, timeout=10000)


@pytest.mark.hardware_free
def test_t4_delete_from_inside_edit_removes_tile(dashboard: Page, clean_up):
    page = dashboard
    _create(page)

    _tile(page).get_by_role("button", name="Edit").click()
    expect(page.get_by_role("button", name="Delete", exact=True)).to_be_visible(timeout=10000)
    # Edit view's own Delete button opens a confirm dialog ("Delete testbed
    # — Remove <name> from the unit?") with its own Delete button — same
    # dialog the card-icon path uses, just triggered from inside the editor.
    # Once the dialog is open, both buttons match role name "Delete"
    # exact=True (the dimmed edit-view button behind the overlay, plus the
    # dialog's own) — .btn-danger scopes to the confirm dialog's button.
    page.get_by_role("button", name="Delete", exact=True).click()
    page.locator("button.btn-danger", has_text="Delete").click()

    # Deleting from inside Edit navigates back to the dashboard.
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    expect(_tile(page)).to_have_count(0, timeout=10000)
