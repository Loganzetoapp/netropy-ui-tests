"""T8 — The per-port selector switches the donut to that port's mix.

Confirmed by exploration: pinning one stream's Interface Port ID to
Port 1 and another's to Port 2 (via the Streams step, not "All ports"),
the Traffic profile donut shows only that port's own stream at 100%
when its dropdown is selected — genuinely different mixes per port, not
just a relabeled view of the same shared data.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-PerPortSelector-DeleteMe"


@pytest.mark.hardware_free
def test_t8_per_port_selector_shows_that_ports_own_mix(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).add_stream("UDP")

    stream_rows = TestbedEditorPage(page).stream_rows()
    stream_rows.nth(0).locator("select").first.select_option("1")
    stream_rows.nth(1).locator("select").first.select_option("2")

    TestbedEditorPage(page).open_load_profile()

    port_select = page.locator("span", has_text="Traffic profile").locator(
        "xpath=following-sibling::span[1]"
    ).locator("select")
    expect(port_select).to_have_value("1")
    expect(page.get_by_text("udp-1", exact=True)).to_be_visible()
    expect(page.get_by_text("udp-2", exact=True)).to_have_count(0)

    port_select.select_option("2")
    expect(page.get_by_text("udp-2", exact=True)).to_be_visible()
    expect(page.get_by_text("udp-1", exact=True)).to_have_count(0)
