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

from pages import DashboardPage

NAME = "T5-UseToggle-DeleteMe"


@pytest.mark.hardware_free
def test_t5_use_toggle_enables_and_disables_row_controls(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

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
