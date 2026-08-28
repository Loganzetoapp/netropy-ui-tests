"""T7 — Wizard step 3 (Streams): Add Stream creates a row with an auto-generated name.

Confirmed by exploration: the Add Stream modal's "Name (prefix when
adding several)" field defaults to the protocol's lowercase name (e.g.
"udp") but the actual created row gets a "-1" suffix appended
automatically ("udp-1"), and a second Add Stream increments to "udp-2".
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T7-AddStream-DeleteMe"


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
    # Both the Ports roster table and the Streams table share the
    # `dev-table` class; the Ports accordion panel stays expanded
    # alongside Streams throughout this flow (confirmed by exploration —
    # opening a later step doesn't auto-collapse earlier ones), so the
    # Streams table is reliably the 2nd `.dev-table` on the page.
    return page.locator("table.dev-table").nth(1).locator("tbody tr")


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t7_add_stream_names_auto_increment(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    rows = _stream_rows(page)

    _add_stream(page)
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator("td").first.locator("input")).to_have_value("udp-1")

    _add_stream(page)
    expect(rows).to_have_count(2)
    expect(rows.nth(1).locator("td").first.locator("input")).to_have_value("udp-2")
