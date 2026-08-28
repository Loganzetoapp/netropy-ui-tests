"""T4 — Create testbed: name + module → card appears, counter increments.

Selector note: the per-card action icons (export/clone/delete) have no
accessible name or data-testid — only a `data-tip` attribute used for the
hover tooltip. `data-tip` is the closest thing to a stable identifier here
and is used for scoping instead of position, but a real data-testid would
be preferable; worth requesting from the frontend team (see T4 plan note).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T4-Create-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _saved_count(page: Page) -> int:
    text = page.locator(".card").filter(has_text="Testbeds").get_by_text(
        "saved", exact=False
    ).inner_text()
    return int(text.split("saved")[0].strip())


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_if_present(dashboard)
    yield
    _delete_if_present(dashboard)


@pytest.mark.hardware_free
def test_t4_create_testbed_adds_card_and_increments_counter(dashboard: Page, clean_up):
    page = dashboard
    before = _saved_count(page)

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()

    tile = _tile(page)
    expect(tile).to_have_count(1, timeout=10000)
    expect(tile).to_contain_text("Traffic Engine")
    assert _saved_count(page) == before + 1
