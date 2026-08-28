"""T7 — Frame size bounds: below 64, above the jumbo max (9216), non-numeric.

Unlike the wizard step-1 Line Rate field (T5) and step-2 IP/MAC fields
(T6), this field DOES declare real `min="64" max="9216"` attributes —
but, consistent with the app's general pattern, nothing enforces them:
values below 64 and above 9216 are both accepted verbatim with no error
and no clamping on blur. Documented as a gap, not routed around.
Non-numeric text can't be typed at all (native `<input type="number">`
behavior, same as T5/T6).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T7-FrameSizeBounds-DeleteMe"


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
def test_t7_frame_size_below_64_accepted_without_clamping(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    frame_input = _stream_rows(page).first.locator("td:nth-child(5) input")

    assert frame_input.get_attribute("min") == "64"
    frame_input.fill("32")
    frame_input.press("Tab")
    expect(frame_input).to_have_value("32")


@pytest.mark.hardware_free
def test_t7_frame_size_above_9216_accepted_without_clamping(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    frame_input = _stream_rows(page).first.locator("td:nth-child(5) input")

    assert frame_input.get_attribute("max") == "9216"
    frame_input.fill("50000")
    frame_input.press("Tab")
    expect(frame_input).to_have_value("50000")


@pytest.mark.hardware_free
def test_t7_frame_size_rejects_non_numeric_keystrokes(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    frame_input = _stream_rows(page).first.locator("td:nth-child(5) input")

    with pytest.raises(Exception):
        frame_input.fill("abc")
