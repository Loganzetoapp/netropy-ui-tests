"""T6 — Invalid IP/MAC input: no client-side validation at all.

Plan asked to test malformed IP, out-of-range octet, and bad MAC format.
Confirmed by exploration: all three are plain text inputs with no
pattern/validation — "not.an.ip", "10.0.0.999", and
"zz:zz:zz:zz:zz:zz" are all accepted verbatim, no error shown, no
clearing on blur (unlike the wizard step-1 Line Rate field, which does
clear invalid values — see T5). Documented as a real gap rather than
routed around; not asserting a validation behavior that doesn't exist.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-InvalidInput-DeleteMe"


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
def test_t6_malformed_source_ip_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    ip_input = port1.locator('input[placeholder="10.1.0.10"]')

    ip_input.fill("not.an.ip")
    ip_input.press("Tab")
    expect(ip_input).to_have_value("not.an.ip")


@pytest.mark.hardware_free
def test_t6_out_of_range_octet_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    ip_input = port1.locator('input[placeholder="10.1.0.10"]')

    ip_input.fill("10.0.0.999")
    ip_input.press("Tab")
    expect(ip_input).to_have_value("10.0.0.999")


@pytest.mark.hardware_free
def test_t6_bad_mac_format_accepted_without_error(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first
    mac_input = port1.locator('input[placeholder="02:00:00:00:00:01"]')

    mac_input.fill("zz:zz:zz:zz:zz:zz")
    mac_input.press("Tab")
    expect(mac_input).to_have_value("zz:zz:zz:zz:zz:zz")
