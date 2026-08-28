"""T6 — Cards/Table view toggle: a value edited in one view shows in the other.

Confirmed by exploration: the Cards/Table toggle is a `role="tablist"`
pair labelled "▦ Cards" / "▤ Table" (same pattern as the Roster/Topology
toggle in T5). Table view renders one row per port with the same fields
as columns. Editing Port 1's Source IP in Cards view and switching to
Table view shows the edited value there too.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-CardsTable-DeleteMe"


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


def _create_and_open_network_config(page: Page, name: str = NAME):
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
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    page.get_by_role("button", name="Next", exact=False).click()
    expect(page.locator(".ne-pcard").first).to_be_visible(timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t6_ip_edited_in_cards_view_appears_in_table_view(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
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
