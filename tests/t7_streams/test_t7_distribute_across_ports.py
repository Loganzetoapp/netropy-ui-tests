"""T7 — "Distribute across ports" bulk-assigns each stream's Interface Port ID.

Confirmed by exploration these are one-shot bulk-apply actions (no
persistent selected/active state), same pattern as the network-config
🔗 auto-fill buttons in T6 — not a toggle. With 3 streams across 2 ports:
- All Ports: every stream's Interface Port ID is "all"
- Alternate (round-robin): 1, 2, 1
- Sequence (contiguous blocks): 1, 1, 2
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T7-Distribute-DeleteMe"


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
def test_t7_distribute_across_ports_alternate_vs_sequence(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    for _ in range(3):
        _add_stream(page)
    rows = _stream_rows(page)
    expect(rows).to_have_count(3)
    port_id_selects = [rows.nth(i).locator("select").first for i in range(3)]

    for sel in port_id_selects:
        expect(sel).to_have_value("all")

    # Not get_by_role(..., exact=True): the button's own accessible name
    # computation ends up not exactly "Alternate"/"Sequence"/"All Ports"
    # (likely folding in its data-tip description) even though the
    # visible text and innerText are exactly that — exact=True finds 0
    # matches while the fuzzy default finds exactly 1, unambiguously.
    page.get_by_role("button", name="Sequence").click()
    expect(port_id_selects[0]).to_have_value("1")
    expect(port_id_selects[1]).to_have_value("1")
    expect(port_id_selects[2]).to_have_value("2")

    page.get_by_role("button", name="Alternate").click()
    expect(port_id_selects[0]).to_have_value("1")
    expect(port_id_selects[1]).to_have_value("2")
    expect(port_id_selects[2]).to_have_value("1")

    page.get_by_role("button", name="All Ports").click()
    for sel in port_id_selects:
        expect(sel).to_have_value("all")
