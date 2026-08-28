"""T13 — Connectivity Diagnostics (deferred, WORK IN PROGRESS in the UI).

Per the test plan: this whole area is marked work-in-progress in the
product, and ARP/Ping/Traceroute are live network actions that belong
in an integration tier, not this UI suite. The only thing worth
asserting now is that DHCP Pre-Acq renders as not supported/disabled —
confirmed by exploration: the card is visually dimmed (`opacity: 0.55`)
with `pointer-events: none` on its controls, a `title` explaining why
("Not supported — the datapath has no DHCP client"), and its toggle is
present but inert. This only needs 2 ports enabled — no streams, no
port reservation beyond the wizard's own client-side USE toggle (which,
per T5, fires no network request).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T13-DhcpPreAcq-DeleteMe"


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=NAME)


def _delete_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _cleanup_from_wherever(page: Page):
    if _testbed_tile(page).count() > 0:
        _delete_if_present(page)
        return
    delete_btn = page.get_by_role("button", name="Delete", exact=True)
    if delete_btn.count() > 0 and delete_btn.first.is_visible():
        delete_btn.first.click()
        page.locator("button.btn-danger", has_text="Delete").click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    _delete_if_present(page)


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t13_dhcp_pre_acq_renders_not_supported(dashboard: Page, clean_up):
    page = dashboard
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _testbed_tile(page)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()

    page.get_by_role("button", name="4 Traffic and Load Profile", exact=False).click()
    diagnostics_summary = page.get_by_text("Connectivity diagnostics", exact=False)
    expect(diagnostics_summary).to_be_visible(timeout=10000)
    diagnostics_summary.click()

    dhcp_card = page.locator(".diag-card", has_text="DHCP Pre-Acq")
    expect(dhcp_card).to_be_visible()
    expect(dhcp_card).to_have_attribute(
        "title", "Not supported — the datapath has no DHCP client"
    )
    expect(dhcp_card.get_by_text("Not supported", exact=False)).to_be_visible()
    # The toggle isn't a native-disabled input — the whole card is inert
    # via CSS (`pointer-events: none` on its actions, dimmed opacity),
    # confirmed by exploration. Clicking it should have no effect.
    toggle = dhcp_card.locator(".toggle .track")
    checkbox = dhcp_card.locator('input[type="checkbox"]')
    expect(checkbox).not_to_be_checked()
    toggle.click(force=True)
    expect(checkbox).not_to_be_checked()
