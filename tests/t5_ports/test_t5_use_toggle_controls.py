"""T5 — Wizard step 1 (Ports): the USE toggle enables/disables the row.

Confirmed by exploration: with USE off, the row's Multisite checkbox,
Direction/Peer Port selects, and Line Rate input+unit select all carry
the `disabled` attribute and the row is dimmed (`opacity: 0.65`); with
USE on, none of them are disabled and opacity is reset to 1. Toggling a
port's USE checkbox alone — never clicking Save/Apply — does not touch
port reservation state on the unit (confirmed: no network request fires
on toggle, and the dashboard's Port Status table is unaffected), so this
whole file is hardware_free even though it drives the wizard.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-UseToggle-DeleteMe"


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
def test_t5_use_toggle_enables_and_disables_row_controls(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

    row1 = page.locator("tr").nth(1)
    rate_input = row1.locator('input[placeholder="line rate"]')
    unit_select = row1.locator("select").nth(2)
    direction_select = row1.locator("select").nth(0)
    peer_select = row1.locator("select").nth(1)
    multisite_checkbox = row1.locator('input[type="checkbox"]').nth(1)

    # USE off (default): everything else in the row is disabled.
    expect(rate_input).to_be_disabled()
    expect(unit_select).to_be_disabled()
    expect(direction_select).to_be_disabled()
    expect(peer_select).to_be_disabled()
    expect(multisite_checkbox).to_be_disabled()

    row1.locator(".toggle .track").click()

    # USE on: controls become interactive.
    expect(rate_input).to_be_enabled()
    expect(unit_select).to_be_enabled()
    expect(direction_select).to_be_enabled()
    expect(peer_select).to_be_enabled()
    expect(multisite_checkbox).to_be_enabled()

    row1.locator(".toggle .track").click()

    # Back off: disabled again.
    expect(rate_input).to_be_disabled()
    expect(unit_select).to_be_disabled()
