"""T6 — IP Inc interacts with the host range correctly.

Confirmed by exploration: IP Inc is disabled while there's only 1 host
(/32). Once the subnet is widened (/25, 126 hosts) IP Inc becomes
editable, and changing it changes how far the displayed range steps —
the host *count* stays 126 either way, but the range's end address
changes based on the increment (IP Inc=5 over 126 hosts steps into the
next octet: 10.0.0.2 -> 10.0.2.115).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-IPInc-DeleteMe"


@pytest.mark.hardware_free
def test_t6_ip_inc_disabled_at_one_host_enabled_above(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    ip_inc = port1.locator(".ne-src-asn").nth(1).locator("input")

    expect(ip_inc).to_be_disabled()
    port1.locator("select.seg").select_option("25")
    expect(ip_inc).to_be_enabled()


@pytest.mark.hardware_free
def test_t6_ip_inc_changes_range_end_not_host_count(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    ip_inc = port1.locator(".ne-src-asn").nth(1).locator("input")
    range_text = port1.locator(".ne-src-range")
    hosts_badge = port1.locator(".ne-src-rail div div div").first

    port1.locator("select.seg").select_option("25")
    expect(range_text).to_have_text("10.0.0.2 → 10.0.0.127 (126 hosts)")

    ip_inc.fill("5")
    ip_inc.press("Tab")
    expect(range_text).to_have_text("10.0.0.2 → 10.0.2.115 (126 hosts)")
    expect(hosts_badge).to_have_text("126")
