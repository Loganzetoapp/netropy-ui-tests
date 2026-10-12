"""T7 — Wizard step 3 (Streams): Add Stream creates a row with an auto-generated name.

Confirmed by exploration: the Add Stream modal's "Name (prefix when
adding several)" field defaults to the protocol's lowercase name (e.g.
"udp") but the actual created row gets a "-1" suffix appended
automatically ("udp-1"), and a second Add Stream increments to "udp-2".
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-AddStream-DeleteMe"


@pytest.mark.hardware_free
def test_t7_add_stream_names_auto_increment(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    rows = TestbedEditorPage(page).stream_rows()

    TestbedEditorPage(page).add_stream("UDP")
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator("td").first.locator("input")).to_have_value("udp-1")

    TestbedEditorPage(page).add_stream("UDP")
    expect(rows).to_have_count(2)
    expect(rows.nth(1).locator("td").first.locator("input")).to_have_value("udp-2")
