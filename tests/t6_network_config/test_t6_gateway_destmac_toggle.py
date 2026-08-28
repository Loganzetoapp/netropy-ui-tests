"""T6 — Gateway vs Dest MAC segmented toggle: each side remembers its own value.

Confirmed by exploration: switching to Gateway the very first time shows
an empty field (there's nothing to carry over from a MAC address into an
IP field). But once a Gateway IP has actually been typed, toggling back
and forth between Gateway and Dest MAC preserves each mode's own value
independently — neither one clears the other.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-GatewayToggle-DeleteMe"


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
def test_t6_gateway_destmac_toggle_preserves_each_value(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first

    seg2 = port1.locator('.ne-seg2[role="tablist"]')
    gateway_tab = seg2.get_by_role("tab", name="Gateway")
    destmac_tab = seg2.get_by_role("tab", name="Dest MAC")
    nexthop_input = port1.locator(".ne-dst-row input")

    original_mac = nexthop_input.input_value()
    assert original_mac  # auto-filled Dest MAC from the peer port

    gateway_tab.click()
    expect(nexthop_input).to_have_value("")
    expect(nexthop_input).to_have_attribute("placeholder", "gateway IP")

    nexthop_input.fill("10.9.9.9")
    nexthop_input.press("Tab")
    expect(nexthop_input).to_have_value("10.9.9.9")

    destmac_tab.click()
    expect(nexthop_input).to_have_value(original_mac)

    gateway_tab.click()
    expect(nexthop_input).to_have_value("10.9.9.9")
