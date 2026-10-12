"""T6 — Gateway vs Dest MAC segmented toggle: each side remembers its own value.

Confirmed by exploration: switching to Gateway the very first time shows
an empty field (there's nothing to carry over from a MAC address into an
IP field). But once a Gateway IP has actually been typed, toggling back
and forth between Gateway and Dest MAC preserves each mode's own value
independently — neither one clears the other.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-GatewayToggle-DeleteMe"


@pytest.mark.hardware_free
def test_t6_gateway_destmac_toggle_preserves_each_value(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first

    seg2 = port1.locator('.ne-seg2[role="tablist"]')
    gateway_tab = seg2.get_by_role("tab", name="Gateway")
    destmac_tab = seg2.get_by_role("tab", name="Dest MAC")
    nexthop_input = port1.locator(".ne-dst-row input")

    original_mac = nexthop_input.input_value()
    assert original_mac  # auto-filled Dest MAC from the peer port

    gateway_tab.click()
    expect(nexthop_input).to_have_value("")
    expect(nexthop_input).to_have_attribute("placeholder", "gateway IP")

    nexthop_input.fill("10.9.9.9")
    nexthop_input.press("Tab")
    expect(nexthop_input).to_have_value("10.9.9.9")

    destmac_tab.click()
    expect(nexthop_input).to_have_value(original_mac)

    gateway_tab.click()
    expect(nexthop_input).to_have_value("10.9.9.9")
