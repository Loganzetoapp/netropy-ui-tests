"""T7 — Frame size "Apply to all" overwrites per-row values; a later
per-row edit sticks until the next apply-to-all.

Confirmed by exploration: editing one row's Frame size leaves the other
row untouched; clicking "Apply to all" overwrites every row; editing a
row again afterward only changes that row, leaving the others at
whatever "Apply to all" last set.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-FrameSizeApply-DeleteMe"


@pytest.mark.hardware_free
def test_t7_frame_size_apply_to_all_then_per_row_edit_sticks(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    rows = TestbedEditorPage(page).stream_rows()
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).add_stream("UDP")

    row1_frame = rows.nth(0).locator("td:nth-child(5) input")
    row2_frame = rows.nth(1).locator("td:nth-child(5) input")
    expect(row1_frame).to_have_value("1500")
    expect(row2_frame).to_have_value("1500")

    row1_frame.fill("512")
    row1_frame.press("Tab")
    expect(row1_frame).to_have_value("512")
    expect(row2_frame).to_have_value("1500")  # untouched

    apply_all_input = page.locator("div", has_text="Frame size").locator(
        'input[min="64"]'
    ).first
    apply_all_input.fill("900")
    page.get_by_role("button", name="Apply to all", exact=True).click()
    expect(row1_frame).to_have_value("900")
    expect(row2_frame).to_have_value("900")

    row1_frame.fill("777")
    row1_frame.press("Tab")
    expect(row1_frame).to_have_value("777")
    expect(row2_frame).to_have_value("900")  # sticks until the next apply-to-all
