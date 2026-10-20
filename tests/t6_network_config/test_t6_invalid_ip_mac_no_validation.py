"""T6 — Invalid IP/MAC input: no client-side validation at all.

Plan asked to test malformed IP, out-of-range octet, and bad MAC format.
Confirmed by exploration: all three are plain text inputs with no
pattern/validation — "not.an.ip", "10.0.0.999", and
"zz:zz:zz:zz:zz:zz" are all accepted verbatim, no error shown, no
clearing on blur (unlike the wizard step-1 Line Rate field, which does
clear invalid values — see T5). Documented as a real gap rather than
routed around; not asserting a validation behavior that doesn't exist.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T6-InvalidInput-DeleteMe"


@pytest.mark.hardware_free
def test_t6_malformed_source_ip_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    ip_input = port1.locator('input[placeholder="10.1.0.10"]')

    ip_input.fill("not.an.ip")
    ip_input.press("Tab")
    expect(ip_input).to_have_value("not.an.ip")


@pytest.mark.hardware_free
def test_t6_out_of_range_octet_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    ip_input = port1.locator('input[placeholder="10.1.0.10"]')

    ip_input.fill("10.0.0.999")
    ip_input.press("Tab")
    expect(ip_input).to_have_value("10.0.0.999")


@pytest.mark.hardware_free
def test_t6_bad_mac_format_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=2, network_view="Cards")
    port1 = page.locator(".ne-pcard").first
    mac_input = port1.locator('input[placeholder="02:00:00:00:00:01"]')

    mac_input.fill("zz:zz:zz:zz:zz:zz")
    mac_input.press("Tab")
    expect(mac_input).to_have_value("zz:zz:zz:zz:zz:zz")
