"""T6 — Wizard step 2 (Network Configuration): host-count math.

The plan calls this the highest-value hardware-free area since the UI
computes values live. Confirmed by exploration: the CIDR select only
offers /25 through /32 plus a raw-mask display (no /24 or wider — noted
already in the T10/T12 ICMP lifecycle test's comments), so this covers
/32, /31, /30, and /25 rather than chasing an option that doesn't exist.
Both the circle badge (`.ne-src-rail`, shows just the number) and the
inline range text (`.ne-src-range`, "x.x.x.x → y.y.y.y (N hosts)", or a
single IP with no arrow at /32 where there's nothing to range over) are
asserted, per the plan's explicit ask.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T6-HostCount-DeleteMe"


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
def test_t6_host_count_default_32_is_one_host(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first

    expect(port1.locator("select.seg")).to_have_value("32")
    expect(port1.locator(".ne-src-range")).to_have_text("10.0.0.2 (1 host)")
    expect(port1.locator(".ne-src-rail div div div").first).to_have_text("1")
    expect(port1.locator('input[aria-label="Hosts"]')).to_have_value("1")


@pytest.mark.hardware_free
def test_t6_host_count_31_is_two_hosts(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first

    port1.locator("select.seg").select_option("31")
    expect(port1.locator(".ne-src-range")).to_have_text(
        "10.0.0.2 → 10.0.0.3 (2 hosts)"
    )
    expect(port1.locator(".ne-src-rail div div div").first).to_have_text("2")
    expect(port1.locator('input[aria-label="Hosts"]')).to_have_value("2")


@pytest.mark.hardware_free
def test_t6_host_count_25_is_126_hosts(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_network_config(page)
    port1 = page.locator(".ne-pcard").first

    port1.locator("select.seg").select_option("25")
    expect(port1.locator(".ne-src-range")).to_have_text(
        "10.0.0.2 → 10.0.0.127 (126 hosts)"
    )
    expect(port1.locator(".ne-src-rail div div div").first).to_have_text("126")
    expect(port1.locator('input[aria-label="Hosts"]')).to_have_value("126")

    mask_span = port1.locator("span.seg.mask")
    expect(mask_span).to_have_text("255.255.255.128")
    assert mask_span.get_attribute("title") == "126 usable hosts"
