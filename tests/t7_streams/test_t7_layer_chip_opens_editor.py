"""T7 — Layer chips (Ethernet/IPv4/UDP/Payload) open the stream's layer editor.

Confirmed by exploration: clicking a chip opens `.modal-overlay >
.modal-box` titled "<stream-name> · <PROTOCOL>", with its own tab strip
(`.layer-tabs button.layer-tab`, plain buttons — no `role="tab"`, active
one carries class "on") pre-selecting the tab matching the chip clicked.
The Ethernet tab shows per-field overrides (Source/Destination MAC,
placeholder "inherit" — blank means inherit from the port's host); the
`<label>` elements aren't associated to their `<input>` via for/id, so
get_by_label() won't find them — scoped by the wrapping `.fg` div
instead. Only a smoke check that the editor opens to the right tab and
closes via Done — not a full field-by-field override suite per layer.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-LayerChip-DeleteMe"


@pytest.mark.hardware_free
def test_t7_ethernet_chip_opens_editor_on_ethernet_tab(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    row = TestbedEditorPage(page).stream_rows().first

    row.locator('button.layer-chip[data-tip="Edit Ethernet"]').click()

    modal = page.locator(".modal-box")
    expect(modal).to_be_visible()
    expect(modal.locator(".modal-title")).to_have_text("udp-1 · UDP")
    expect(modal.locator("button.layer-tab.on")).to_have_text("Ethernet")
    expect(modal.get_by_text("overrides", exact=False)).to_be_visible()

    source_mac = modal.locator(".fg", has_text="Source MAC").locator("input")
    dest_mac = modal.locator(".fg", has_text="Destination MAC").locator("input")
    expect(source_mac).to_have_attribute("placeholder", "inherit")
    expect(dest_mac).to_have_attribute("placeholder", "inherit")

    modal.get_by_role("button", name="Done", exact=True).click()
    expect(modal).to_have_count(0)
