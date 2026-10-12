"""T8 — Edit-all vs inline pencil edits.

Confirmed by exploration these are two distinct entry points to the same
underlying share data:
- Inline: clicking a stream's `button[title="Click to edit share"]` (the
  "50%" pill next to its name in the donut legend) turns it into a
  number input in place — starting empty, with the prior value shown
  only as a placeholder (not a real value) until something is typed.
- "Edit all" (data-tip "Edit & pin every stream's share") opens a
  richer "Stream Bandwidth" modal: a per-port list on the left (All
  ports / Port 1 / Port 2, each showing its own stream count) and, for
  the selected port, a slider + numeric input per stream, plus its own
  unit toggle and USED/REMAINING readout. Closed via "Done".
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-EditAll-DeleteMe"


@pytest.mark.hardware_free
def test_t8_inline_pencil_click_becomes_editable(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    share_btn = page.locator('div:has(> span:text-is("udp-1"))').locator(
        'button[title="Click to edit share"]'
    )
    expect(share_btn).to_have_text("100%")
    share_btn.click()
    inline_input = page.locator('div:has(> span:text-is("udp-1"))').locator(
        'input[type="number"]'
    )
    # Starts empty with the current value as a placeholder, not a real
    # value — confirmed by exploration.
    expect(inline_input).to_have_value("")
    expect(inline_input).to_have_attribute("placeholder", "100")


@pytest.mark.hardware_free
def test_t8_edit_all_opens_stream_bandwidth_modal(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    page.get_by_role("button", name="Edit all").click()

    modal = page.locator(".modal-box")
    expect(modal.get_by_text("Stream Bandwidth", exact=True)).to_be_visible()
    # "All ports" / "Port 1" / "Port 2" text is ambiguous inside the modal
    # (also appears as a <select> option and in per-row "applies to"
    # captions) — the left-hand port-picker buttons include the stream
    # count in their accessible name, which disambiguates.
    expect(modal.get_by_role("button", name="All ports", exact=False)).to_be_visible()
    expect(modal.get_by_role("button", name="Port 1", exact=False)).to_be_visible()
    expect(modal.get_by_role("button", name="Port 2", exact=False)).to_be_visible()
    expect(
        modal.get_by_text("Drag a slider or type to pin a stream", exact=False)
    ).to_be_visible()

    modal.get_by_role("button", name="Done", exact=True).click()
    expect(modal).to_have_count(0)
