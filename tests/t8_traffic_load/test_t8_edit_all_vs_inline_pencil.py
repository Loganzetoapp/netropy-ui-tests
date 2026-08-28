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

NAME = "T8-EditAll-DeleteMe"


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


def _open_load_profile(page: Page):
    header = page.get_by_role("button", name="4 Traffic and Load Profile", exact=False)
    header.click()
    expect(header).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".pill", has_text="used")).to_be_visible(timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t8_inline_pencil_click_becomes_editable(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _open_load_profile(page)

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
    _create_and_open_streams(page)
    _add_stream(page)
    _add_stream(page)
    _open_load_profile(page)

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
