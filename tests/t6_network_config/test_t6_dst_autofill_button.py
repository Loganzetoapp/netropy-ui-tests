"""T6 — The 🔗 icon next to DST IP / Dest MAC is a one-time sync button,
not a persistent live link.

The plan's phrasing ("chain icon links... — change source, assert
peer's dest follows; toggle the link off, assert it stops following")
assumes a persistent toggle. Confirmed by exploration this isn't how it
works: the fields auto-populate once when a second port is enabled, but
after that, editing Port 1's Source IP does NOT propagate to Port 2's
DST IP automatically — the button (`title="Auto-fill from N src-ip"` /
`"...src-mac"`) has to be clicked again each time to pull the current
value across. There's no on/off state to toggle; it's always available
as a manual "sync now" action. This test asserts the real, confirmed
mechanism instead of the assumed one.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-Autofill-DeleteMe"


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
def test_t6_dst_ip_autofill_is_manual_not_live(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    port2 = page.locator(".ne-pcard").nth(1)

    port1_src_ip = port1.locator('input[placeholder="10.1.0.10"]')
    port2_dst_ip = port2.locator('.ne-dstf input[placeholder="auto"]').first
    port2_dst_link = port2.locator('.ne-dstf button.lnk[title*="src-ip"]')

    expect(port2_dst_ip).to_have_value("10.0.0.2")  # auto-filled on port enable

    port1_src_ip.fill("10.0.0.99")
    port1_src_ip.press("Tab")
    expect(port2_dst_ip).to_have_value("10.0.0.2")  # unchanged — no live link

    port2_dst_link.click()
    expect(port2_dst_ip).to_have_value("10.0.0.99")  # pulled in on click


@pytest.mark.hardware_free
def test_t6_dst_mac_autofill_is_manual_not_live(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    port2 = page.locator(".ne-pcard").nth(1)

    port1_base_mac = port1.locator('input[placeholder="02:00:00:00:00:01"]')
    port2_dst_mac = port2.locator(".ne-dst-row .ne-dstf input").first
    port2_dst_mac_link = port2.locator('.ne-dst-row button.lnk[title*="src-mac"]')

    expect(port2_dst_mac).to_have_value("02:00:00:00:00:01")

    port1_base_mac.fill("02:00:00:00:00:aa")
    port1_base_mac.press("Tab")
    expect(port2_dst_mac).to_have_value("02:00:00:00:00:01")  # unchanged

    port2_dst_mac_link.click()
    expect(port2_dst_mac).to_have_value("02:00:00:00:00:aa")
