"""T6 — Cards/Table view toggle: a value edited in one view shows in the other.

Confirmed by exploration: the Cards/Table toggle is a `role="tablist"`
pair labelled "▦ Cards" / "▤ Table" (same pattern as the Roster/Topology
toggle in T5). Table view renders one row per port with the same fields
as columns. Editing Port 1's Source IP in Cards view and switching to
Table view shows the edited value there too.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-CardsTable-DeleteMe"


@pytest.mark.hardware_free
def test_t6_ip_edited_in_cards_view_appears_in_table_view(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    ip_input = port1.locator('input[placeholder="10.1.0.10"]')

    ip_input.fill("10.5.5.5")
    ip_input.press("Tab")
    expect(ip_input).to_have_value("10.5.5.5")

    page.get_by_role("tab", name="Table", exact=False).click()
    expect(page.locator("table")).to_have_count(1)

    table_row1 = page.locator("table tbody tr").first
    table_ip_input = table_row1.locator("td").nth(1).locator("input")
    expect(table_ip_input).to_have_value("10.5.5.5")

    page.get_by_role("tab", name="Cards", exact=False).click()
    expect(page.locator(".ne-pcard").first).to_be_visible()
