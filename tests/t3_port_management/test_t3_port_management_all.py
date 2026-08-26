"""T3 port management — reservation lifecycle — combined suite.

Both T3 tests together in one file, for a single at-a-glance run of the
whole feature area. Each test also exists standalone in its own file
(test_t3_reserve_port.py, test_t3_release_port.py) so it can be run in
isolation — this means every T3 test runs twice under the default
markers (once here, once standalone), which is intentional: same
coverage, and T3 is cheap enough that the extra runtime doesn't matter.

Port state is global on shared hardware: every test must release what it
reserves, even on failure, so the fixture teardown always attempts a release.
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


@pytest.mark.stateful
def test_t3_release_port_returns_to_available(available_port_row):
    row = available_port_row
    row.get_by_role("button", name="Reserve").click()
    expect(row.get_by_role("button", name="Release")).to_be_visible()

    row.get_by_role("button", name="Release").click()
    expect(row.get_by_text("Available", exact=True)).to_be_visible()
    expect(row.get_by_role("button", name="Reserve")).to_be_visible()
