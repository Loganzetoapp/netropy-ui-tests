"""T5 — Toggling a configured port's USE off then on: config is remembered.

Plan item explicitly asked to "document and assert whether config clears
or is remembered" — confirmed by exploration: setting a custom line rate
and direction, then toggling USE off and back on, leaves both values
intact rather than resetting to defaults (10 Gbps / bidirectional).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-ToggleRetain-DeleteMe"


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
def test_t5_toggle_off_then_on_retains_rate_and_direction(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

    row1 = page.locator("tr").nth(1)
    toggle = row1.locator(".toggle .track")
    rate_input = row1.locator('input[placeholder="line rate"]')
    direction_select = row1.locator("select").nth(0)

    toggle.click()
    expect(rate_input).to_be_enabled()

    rate_input.fill("7")
    rate_input.press("Tab")
    direction_select.select_option(label="tx only")
    expect(rate_input).to_have_value("7")
    expect(direction_select).to_have_value("tx_only")

    toggle.click()  # off
    expect(rate_input).to_be_disabled()
    toggle.click()  # on again
    expect(rate_input).to_be_enabled()

    expect(rate_input).to_have_value("7")
    expect(direction_select).to_have_value("tx_only")
