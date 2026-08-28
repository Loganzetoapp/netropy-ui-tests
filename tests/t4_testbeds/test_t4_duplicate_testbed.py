"""T4 — Duplicate (clone) a testbed: new card, distinct UID.

The card's clone icon is labelled "Clone (without ports)" via its
data-tip tooltip attribute — no accessible name/data-testid, same gap
noted in test_t4_create_testbed.py.

Clicking it opens a confirm dialog ("Clone '<name>' — New testbed name:
<prefilled input>") rather than cloning immediately; the input is
pre-filled with "<name>-copy" and editable. This test accepts the
pre-filled default and confirms via the dialog's own "Clone" button.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T4-Duplicate-DeleteMe"


def _tiles(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_all(page: Page, name: str = NAME):
    tiles = _tiles(page, name)
    # Delete from the end so indices stay valid as cards disappear.
    while tiles.count() > 0:
        before = tiles.count()
        tiles.last.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(tiles).to_have_count(before - 1, timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_all(dashboard)
    yield
    _delete_all(dashboard)


@pytest.mark.hardware_free
def test_t4_duplicate_testbed_creates_card_with_distinct_uid(dashboard: Page, clean_up):
    page = dashboard

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    expect(_tiles(page)).to_have_count(1, timeout=10000)

    original_uid = (
        _tiles(page)
        .locator("span:has-text('UID:') span[data-tip]")
        .first.get_attribute("data-tip")
    )

    _tiles(page).first.locator('[data-tip="Clone (without ports)"] button').click()
    name_input = page.get_by_role("textbox")
    expect(name_input).to_have_value(f"{NAME}-copy", timeout=10000)
    page.get_by_role("button", name="Clone", exact=True).click()

    expect(_tiles(page)).to_have_count(2, timeout=10000)

    uids = {
        span.get_attribute("data-tip")
        for span in _tiles(page).locator("span:has-text('UID:') span[data-tip]").all()
    }
    assert len(uids) == 2, f"expected two distinct UIDs across original + clone, got {uids}"
    assert original_uid in uids
