"""T6 — Encap dropdown renders its options.

Confirmed by exploration: None / VLAN / QinQ, in that order. Selecting
VLAN or QinQ enables the VLAN/Outer/PCP fields next to it (confirmed
disabled while Encap is None) — asserted here as a light smoke check,
not a full VLAN-tagging behavior suite.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-Encap-DeleteMe"


@pytest.mark.hardware_free
def test_t6_encap_dropdown_options_render(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    encap_select = port1.locator(".ne-grp", has_text="Tagging").locator("select")

    expect(encap_select).to_have_value("none")
    assert encap_select.locator("option").all_inner_texts() == ["None", "VLAN", "QinQ"]

    page.get_by_role("tab", name="Table", exact=False).click()
    table_row1 = page.locator("table tbody tr").first
    vlan_input = table_row1.locator("td").nth(13).locator("input")
    expect(vlan_input).to_be_disabled()

    page.get_by_role("tab", name="Cards", exact=False).click()
    expect(encap_select).to_be_visible()
    encap_select.select_option("vlan")

    page.get_by_role("tab", name="Table", exact=False).click()
    table_row1 = page.locator("table tbody tr").first
    vlan_input = table_row1.locator("td").nth(13).locator("input")
    expect(vlan_input).to_be_enabled()
