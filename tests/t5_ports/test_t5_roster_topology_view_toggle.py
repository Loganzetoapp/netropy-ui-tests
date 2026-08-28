"""T5 — Roster/Topology view toggle renders both views.

Confirmed by exploration: the toggle is a `role="tablist"` pair of
`role="tab"` elements labelled "▤ Roster" / "▦ Topology" (not buttons).
Roster view renders the ports as a `<table>`; switching to Topology
drops the table entirely in favor of an SVG-based diagram.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-RosterTopology-DeleteMe"


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
def test_t5_roster_and_topology_views_both_render(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

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
