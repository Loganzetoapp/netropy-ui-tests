"""T8 — Pinning stream shares over 100% warns rather than blocking.

Confirmed by exploration: with 2 streams, pinning the first to 150%
leaves the second at 0% (rebalance has no room left to give it), USED
reads 150%, and a warning line appears: "⚠ Pinned shares exceed 100% on
Port 1 — trim them so the total fits." Nothing is blocked or clamped —
the plan explicitly asked to document block-vs-warn-vs-rebalance
behavior, and the answer here is warn.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-MixOver100-DeleteMe"


def _stream_share_button(page: Page, stream_name: str):
    return page.locator(f'div:has(> span:text-is("{stream_name}"))').locator(
        'button[title="Click to edit share"]'
    )


@pytest.mark.hardware_free
def test_t8_pinning_over_100_percent_warns_not_blocks(dashboard: Page, clean_up):
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
    inp.fill("150")
    inp.press("Tab")

    expect(_stream_share_button(page, "udp-1")).to_have_text("150%")
    expect(_stream_share_button(page, "udp-2")).to_have_text("0%")
    expect(page.locator(".pill", has_text="used")).to_have_text("used 150%")
    expect(
        page.get_by_text("exceed 100%", exact=False)
    ).to_be_visible()
