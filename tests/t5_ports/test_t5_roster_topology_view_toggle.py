"""T5 — Roster/Topology view toggle renders both views.

Confirmed by exploration: the toggle is a `role="tablist"` pair of
`role="tab"` elements labelled "▤ Roster" / "▦ Topology" (not buttons).
Roster view renders the ports as a `<table>`; switching to Topology
drops the table entirely in favor of an SVG-based diagram.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T5-RosterTopology-DeleteMe"


@pytest.mark.hardware_free
def test_t5_roster_and_topology_views_both_render(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

    roster_tab = page.get_by_role("tab", name="Roster", exact=False)
    topology_tab = page.get_by_role("tab", name="Topology", exact=False)

    expect(roster_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("table")).to_have_count(1)

    topology_tab.click()
    expect(topology_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("table")).to_have_count(0)
    expect(page.locator("svg")).not_to_have_count(0)

    roster_tab.click()
    expect(roster_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("table")).to_have_count(1)
