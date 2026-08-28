"""T7 — Enable/disable state per stream persists across wizard navigation.

Confirmed by exploration: the STATE pill (`button.pill`, data-tip
"Disable stream" / text "enabled" displayed uppercase via CSS, flips to
"disabled" on click, class `pill ok` -> `pill muted`).
This test disables a stream, navigates away to a different wizard step
and back, and confirms the disabled state wasn't lost — the plan
explicitly calls out that per-stream enable/disable state should
persist.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T7-StreamState-DeleteMe"


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
def test_t7_stream_disabled_state_persists_across_navigation(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    state_btn = _stream_rows(page).first.locator("button.pill")

    # Displayed uppercase via CSS text-transform; underlying DOM text is
    # lowercase — same trap as the run-history PASS/FAIL badge.
    expect(state_btn).to_have_text("enabled")
    assert "ok" in state_btn.get_attribute("class")

    state_btn.click()
    expect(state_btn).to_have_text("disabled")
    assert "muted" in state_btn.get_attribute("class")

    # Collapse the Streams accordion panel and re-expand it — confirmed by
    # exploration that opening a later step collapses this one (only the
    # first "Ports" panel stays pinned open alongside whichever other step
    # is active), so this is the reliable way to force the panel to
    # re-render from scratch and prove the disabled state wasn't reset.
    streams_header = page.get_by_role("button", name="3 Streams", exact=False)
    streams_header.click()
    expect(streams_header).to_have_attribute("aria-expanded", "false")
    streams_header.click()
    expect(streams_header).to_have_attribute("aria-expanded", "true")

    state_btn = _stream_rows(page).first.locator("button.pill")
    expect(state_btn).to_have_text("disabled")
    assert "muted" in state_btn.get_attribute("class")
