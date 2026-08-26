"""T2 dashboard smoke — Port Status table renders 8 rows.

Standalone split of one test from test_t2_dashboard_all.py so it can run
in isolation; see that file for the full combined T2 suite.

If this passes, auth, fixtures, and connectivity all work.
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t2_port_table_has_8_rows(dashboard: Page):
    for n in range(1, 9):
        expect(dashboard.get_by_role("row", name=f"Port {n}")).to_be_visible()
