"""T8 — Traffic profile unit toggle (%/Gbps/Mbps/bps) converts values.

Confirmed by exploration: a single 100%-share stream on a 10 Gbps
line-rate port displays as "10 Gbps" when the unit is switched — the
value converts rather than resetting/clearing, consistent with every
other unit toggle already confirmed elsewhere in this suite (T5 line
rate, T6 network config).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-UnitToggle-DeleteMe"


@pytest.mark.hardware_free
def test_t8_unit_toggle_converts_share_value(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    share_btn = page.locator('div:has(> span:text-is("udp-1"))').locator(
        'button[title="Click to edit share"]'
    )
    expect(share_btn).to_have_text("100%")

    page.get_by_role("button", name="Gbps", exact=True).click()
    expect(share_btn).to_have_text("10 Gbps")

    page.get_by_role("button", name="%", exact=True).click()
    expect(share_btn).to_have_text("100%")
