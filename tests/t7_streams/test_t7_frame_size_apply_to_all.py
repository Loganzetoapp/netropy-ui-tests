"""T7 — Frame size "Apply to all" overwrites per-row values; a later
per-row edit sticks until the next apply-to-all.

Confirmed by exploration: editing one row's Frame size leaves the other
row untouched; clicking "Apply to all" overwrites every row; editing a
row again afterward only changes that row, leaving the others at
whatever "Apply to all" last set.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T7-FrameSizeApply-DeleteMe"


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
def test_t7_frame_size_apply_to_all_then_per_row_edit_sticks(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    rows = _stream_rows(page)
    _add_stream(page)
    _add_stream(page)

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
