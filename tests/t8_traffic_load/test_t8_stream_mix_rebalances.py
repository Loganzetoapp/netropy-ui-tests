"""T8 — Wizard step 4 (Traffic and Load Profile): stream mix auto-rebalances.

Confirmed by exploration: adding streams auto-splits the mix evenly
(1 stream = 100%, 2 = 50/50, 3 = 33.3/33.3/33.3), and editing one
stream's inline share auto-rebalances the others to keep the total at
100% (set stream 1 to 70% with 2 streams -> stream 2 becomes 30%
automatically). USED/REMAINING are `<span class="pill">` elements whose
DOM text is lowercase ("used 100%"/"remaining 0%") though displayed
uppercase via CSS — same trap as other badges in this app.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-MixRebalance-DeleteMe"


def _stream_share_button(page: Page, stream_name: str):
    return page.locator(f'div:has(> span:text-is("{stream_name}"))').locator(
        'button[title="Click to edit share"]'
    )


@pytest.mark.hardware_free
def test_t8_stream_mix_splits_evenly_on_add(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    # Add both streams up front, on the Streams step, before ever
    # navigating to step 4 — the wizard's accordion only keeps one
    # non-Ports panel expanded at a time and toggles (not just opens) on
    # click, so hopping back and forth between steps is fragile; adding
    # everything needed first and opening Load Profile once avoids it.
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    expect(_stream_share_button(page, "udp-1")).to_have_text("50%")
    expect(_stream_share_button(page, "udp-2")).to_have_text("50%")

    used_pill = page.locator(".pill", has_text="used")
    remaining_pill = page.locator(".pill", has_text="remaining")
    expect(used_pill).to_have_text("used 100%")
    expect(remaining_pill).to_have_text("remaining 0%")


@pytest.mark.hardware_free
def test_t8_editing_one_share_rebalances_the_other(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    share_1 = _stream_share_button(page, "udp-1")
    share_1.click()
    inp = page.locator('div:has(> span:text-is("udp-1"))').locator(
        'input[type="number"]'
    )
    inp.fill("70")
    inp.press("Tab")

    expect(_stream_share_button(page, "udp-1")).to_have_text("70%")
    expect(_stream_share_button(page, "udp-2")).to_have_text("30%")
    expect(page.locator(".pill", has_text="used")).to_have_text("used 100%")
