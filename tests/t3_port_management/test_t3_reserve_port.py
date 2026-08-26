"""T3 port management — reserve a port updates status and Reserved By.

Standalone split of one test from test_t3_port_management_all.py so it
can run in isolation; see that file for the full combined T3 suite.

Port state is global on shared hardware: this test must release what it
reserves, even on failure, so the fixture teardown always attempts a
release.
"""
import pytest
from playwright.sync_api import Page, expect


def _first_available_row(page: Page):
    for n in range(1, 9):
        row = page.get_by_role("row", name=f"Port {n}")
        if row.get_by_text("Available", exact=True).is_visible():
            return row
    pytest.skip("No available port found — all 8 may be reserved by other users")


@pytest.fixture
def available_port_row(dashboard: Page):
    row = _first_available_row(dashboard)
    yield row
    release_button = row.get_by_role("button", name="Release")
    if release_button.is_visible():
        release_button.click()
        expect(row.get_by_text("Available", exact=True)).to_be_visible()


@pytest.mark.stateful
def test_t3_reserve_port_updates_status_and_reserved_by(available_port_row):
    row = available_port_row
    row.get_by_role("button", name="Reserve").click()
    expect(row.get_by_text("Reserved", exact=True)).to_be_visible()
    expect(row).to_contain_text("test")
    expect(row.get_by_role("button", name="Release")).to_be_visible()
