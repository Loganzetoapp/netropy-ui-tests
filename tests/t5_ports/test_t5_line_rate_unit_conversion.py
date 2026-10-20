"""T5 — Line Rate unit dropdown converts the value rather than clearing it.

Confirmed by exploration: 10 Gbps -> switch unit to Mbps -> field becomes
10000; switch back to Gbps -> field returns to 10.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T5-RateUnit-DeleteMe"


@pytest.mark.hardware_free
def test_t5_line_rate_unit_dropdown_converts_value(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)
    row1 = page.locator("tr").nth(1)
    row1.locator(".toggle .track").click()

    rate_input = row1.locator('input[placeholder="line rate"]')
    unit_select = row1.locator("select").nth(2)
    expect(rate_input).to_be_enabled()

    rate_input.fill("10")
    rate_input.press("Tab")
    expect(unit_select).to_have_value("Gbps")
    expect(rate_input).to_have_value("10")

    unit_select.select_option(label="Mbps")
    expect(rate_input).to_have_value("10000")

    unit_select.select_option(label="Gbps")
    expect(rate_input).to_have_value("10")
