"""T6 — IP Inc interacts with the host range correctly.

Confirmed by exploration: IP Inc is disabled while there's only 1 host
(/32). Once the subnet is widened (/25, 126 hosts) IP Inc becomes
editable, and changing it changes how far the displayed range steps —
the host *count* stays 126 either way, but the range's end address
changes based on the increment (IP Inc=5 over 126 hosts steps into the
next octet: 10.0.0.2 -> 10.0.2.115).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-IPInc-DeleteMe"


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


def _create_and_open_network_config(page: Page, name: str = NAME):
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
    page.get_by_role("button", name="Next", exact=False).click()
    expect(page.locator(".ne-pcard").first).to_be_visible(timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t6_ip_inc_disabled_at_one_host_enabled_above(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    ip_inc = port1.locator(".ne-src-asn").nth(1).locator("input")

    expect(ip_inc).to_be_disabled()
    port1.locator("select.seg").select_option("25")
    expect(ip_inc).to_be_enabled()


@pytest.mark.hardware_free
def test_t6_ip_inc_changes_range_end_not_host_count(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    ip_inc = port1.locator(".ne-src-asn").nth(1).locator("input")
    range_text = port1.locator(".ne-src-range")
    hosts_badge = port1.locator(".ne-src-rail div div div").first

    port1.locator("select.seg").select_option("25")
    expect(range_text).to_have_text("10.0.0.2 → 10.0.0.127 (126 hosts)")

    ip_inc.fill("5")
    ip_inc.press("Tab")
    expect(range_text).to_have_text("10.0.0.2 → 10.0.2.115 (126 hosts)")
    expect(hosts_badge).to_have_text("126")
