"""T8 — The per-port selector switches the donut to that port's mix.

Confirmed by exploration: pinning one stream's Interface Port ID to
Port 1 and another's to Port 2 (via the Streams step, not "All ports"),
the Traffic profile donut shows only that port's own stream at 100%
when its dropdown is selected — genuinely different mixes per port, not
just a relabeled view of the same shared data.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T8-PerPortSelector-DeleteMe"


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
def test_t8_per_port_selector_shows_that_ports_own_mix(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _add_stream(page)

    stream_rows = page.locator("table.dev-table").nth(1).locator("tbody tr")
    stream_rows.nth(0).locator("select").first.select_option("1")
    stream_rows.nth(1).locator("select").first.select_option("2")

    _open_load_profile(page)

    port_select = page.locator("span", has_text="Traffic profile").locator(
        "xpath=following-sibling::span[1]"
    ).locator("select")
    expect(port_select).to_have_value("1")
    expect(page.get_by_text("udp-1", exact=True)).to_be_visible()
    expect(page.get_by_text("udp-2", exact=True)).to_have_count(0)

    port_select.select_option("2")
    expect(page.get_by_text("udp-2", exact=True)).to_be_visible()
    expect(page.get_by_text("udp-1", exact=True)).to_have_count(0)
