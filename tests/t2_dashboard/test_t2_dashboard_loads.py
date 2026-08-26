"""T2 dashboard smoke — dashboard loads with header and Port Status.

Standalone split of one test from test_t2_dashboard_all.py so it can run
in isolation; see that file for the full combined T2 suite.

If this passes, auth, fixtures, and connectivity all work.
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_dashboard_loads(dashboard: Page):
    expect(dashboard.get_by_text("Netropy Traffic Generator", exact=True)).to_be_visible()
    expect(dashboard.get_by_text("Port Status")).to_be_visible()
