"""T5 — Toggling a configured port's USE off then on: config is remembered.

Plan item explicitly asked to "document and assert whether config clears
or is remembered" — confirmed by exploration: setting a custom line rate
and direction, then toggling USE off and back on, leaves both values
intact rather than resetting to defaults (10 Gbps / bidirectional).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T5-ToggleRetain-DeleteMe"


@pytest.mark.hardware_free
def test_t5_toggle_off_then_on_retains_rate_and_direction(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

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
