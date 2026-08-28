"""T4 — Create testbed validation: empty name and duplicate name.

Selector note: same data-tip based icon scoping as test_t4_create_testbed.py
(no accessible name / data-testid on the icon-only card buttons).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T4-Validation-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_if_present(dashboard)
    yield
    _delete_if_present(dashboard)


@pytest.mark.hardware_free
def test_t4_create_empty_name_disables_create_draft(dashboard: Page, clean_up):
    page = dashboard
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_role("button", name="Traffic Engine", exact=True).click()

    # Name field left empty — "Create draft" must not be clickable.
    create_btn = page.get_by_role("button", name="Create draft", exact=True)
    expect(create_btn).to_be_disabled()


@pytest.mark.hardware_free
def test_t4_create_duplicate_name_shows_inline_error(dashboard: Page, clean_up):
    page = dashboard

    # First testbed with NAME succeeds.
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    expect(_tile(page)).to_have_count(1, timeout=10000)

    # Second attempt with the same name is rejected with an inline error,
    # and no second card is created.
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()

    expect(page.get_by_text(f"a config named '{NAME}' already exists")).to_be_visible()
    expect(_tile(page)).to_have_count(1)

    # Back out of the still-open dialog so teardown finds a clean dashboard.
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.get_by_placeholder("e.g. web-perf-01")).to_have_count(0)
