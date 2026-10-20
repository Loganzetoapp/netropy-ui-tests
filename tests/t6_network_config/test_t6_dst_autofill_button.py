"""T6 — The 🔗 icon next to DST IP / Dest MAC is a one-time sync button,
not a persistent live link.

The plan's phrasing ("chain icon links... — change source, assert
peer's dest follows; toggle the link off, assert it stops following")
assumes a persistent toggle. Confirmed by exploration this isn't how it
works: the fields auto-populate once when a second port is enabled, but
after that, editing Port 1's Source IP does NOT propagate to Port 2's
DST IP automatically — the button (`title="Auto-fill from N src-ip"` /
`"...src-mac"`) has to be clicked again each time to pull the current
value across. There's no on/off state to toggle; it's always available
as a manual "sync now" action. This test asserts the real, confirmed
mechanism instead of the assumed one.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-Autofill-DeleteMe"


@pytest.mark.hardware_free
def test_t6_dst_ip_autofill_is_manual_not_live(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    port2 = page.locator(".ne-pcard").nth(1)

    port1_src_ip = port1.locator('input[placeholder="10.1.0.10"]')
    port2_dst_ip = port2.locator('.ne-dstf input[placeholder="auto"]').first
    port2_dst_link = port2.locator('.ne-dstf button.lnk[title*="src-ip"]')

    expect(port2_dst_ip).to_have_value("10.0.0.2")  # auto-filled on port enable

    port1_src_ip.fill("10.0.0.99")
    port1_src_ip.press("Tab")
    expect(port2_dst_ip).to_have_value("10.0.0.2")  # unchanged — no live link

    port2_dst_link.click()
    expect(port2_dst_ip).to_have_value("10.0.0.99")  # pulled in on click


@pytest.mark.hardware_free
def test_t6_dst_mac_autofill_is_manual_not_live(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    port2 = page.locator(".ne-pcard").nth(1)

    port1_base_mac = port1.locator('input[placeholder="02:00:00:00:00:01"]')
    port2_dst_mac = port2.locator(".ne-dst-row .ne-dstf input").first
    port2_dst_mac_link = port2.locator('.ne-dst-row button.lnk[title*="src-mac"]')

    expect(port2_dst_mac).to_have_value("02:00:00:00:00:01")

    port1_base_mac.fill("02:00:00:00:00:aa")
    port1_base_mac.press("Tab")
    expect(port2_dst_mac).to_have_value("02:00:00:00:00:01")  # unchanged

    port2_dst_mac_link.click()
    expect(port2_dst_mac).to_have_value("02:00:00:00:00:aa")
