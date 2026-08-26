"""T2 dashboard smoke — Licenses section shows license gating.

Standalone split of one test from test_t2_dashboard_all.py so it can run
in isolation; see that file for the full combined T2 suite.

If this passes, auth, fixtures, and connectivity all work.
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_licenses_section_shows_gating(dashboard: Page):
    licenses_card = dashboard.locator(".card", has=dashboard.get_by_role("heading", name="Licenses"))
    expect(licenses_card.get_by_text("Traffic Engine", exact=True)).to_be_visible()
    expect(licenses_card.get_by_text("RFC 2544", exact=True)).to_be_visible()
    expect(licenses_card.get_by_text("SessionStrike", exact=True)).to_be_visible()
