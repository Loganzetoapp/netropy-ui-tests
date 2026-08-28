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

NAME = "T7-LayerChip-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _cleanup_from_wherever(page: Page, name: str = NAME):
    if _tile(page, name).count() > 0:
        _delete_if_present(page, name)
        return
    delete_btn = page.get_by_role("button", name="Delete", exact=True)
    if delete_btn.count() > 0 and delete_btn.first.is_visible():
        delete_btn.first.click()
        page.locator("button.btn-danger", has_text="Delete").click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    _delete_if_present(page, name)


def _create_and_open_streams(page: Page, name: str = NAME):
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _tile(page, name)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    page.get_by_role("button", name="3 Streams", exact=False).click()
    expect(page.get_by_role("button", name="✚ Add Stream", exact=True)).to_be_visible(
        timeout=10000
    )


def _add_stream(page: Page):
    page.get_by_role("button", name="✚ Add Stream", exact=True).click()
    expect(page.get_by_role("button", name="Add stream", exact=True)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="Add stream", exact=True).click()


def _stream_rows(page: Page):
    return page.locator("table.dev-table").nth(1).locator("tbody tr")


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t7_ethernet_chip_opens_editor_on_ethernet_tab(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    row = _stream_rows(page).first

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
