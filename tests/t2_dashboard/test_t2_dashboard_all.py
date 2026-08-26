"""T2 dashboard smoke tests — combined suite.

All 3 T2 tests together in one file, for a single at-a-glance run of the
whole feature area. Each test also exists standalone in its own file
(test_t2_dashboard_loads.py, test_t2_port_table_has_8_rows.py,
test_t2_licenses_section_shows_gating.py) so it can be run in isolation —
this means every T2 test runs twice under the default markers (once
here, once standalone), which is intentional: same coverage, and T2 is
cheap enough that the extra runtime doesn't matter.

If these pass, auth, fixtures, and connectivity all work.
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_dashboard_loads(dashboard: Page):
    expect(dashboard.get_by_text("Netropy Traffic Generator", exact=True)).to_be_visible()
    expect(dashboard.get_by_text("Port Status")).to_be_visible()


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_port_table_has_8_rows(dashboard: Page):
    for n in range(1, 9):
        expect(dashboard.get_by_role("row", name=f"Port {n}")).to_be_visible()


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_licenses_section_shows_gating(dashboard: Page):
    licenses_card = dashboard.locator(".card", has=dashboard.get_by_role("heading", name="Licenses"))
    expect(licenses_card.get_by_text("Traffic Engine", exact=True)).to_be_visible()
    expect(licenses_card.get_by_text("RFC 2544", exact=True)).to_be_visible()
    expect(licenses_card.get_by_text("SessionStrike", exact=True)).to_be_visible()
