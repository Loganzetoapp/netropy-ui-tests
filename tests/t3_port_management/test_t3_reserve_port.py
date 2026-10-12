"""T3 port management — reserve a port updates status and Reserved By.

Port state is global on shared hardware: this test must release what it
reserves, even on failure, so the fixture teardown always attempts a
release.

On pages/ (2026-10-11).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, settings


@pytest.fixture
def free_port(dashboard: Page):
    """A port nobody holds; released again afterwards if this test left it
    reserved (it only ever releases the port it picked)."""
    board = DashboardPage(dashboard)
    port = board.first_unreserved_port()
    if port is None:
        pytest.skip("No unreserved port: all 8 may be held by other users")
    yield port
    if board.port_row(port).get_by_role("button", name="Release", exact=True).is_visible():
        board.release_port(port)


@pytest.mark.stateful
def test_t3_reserve_port_updates_status_and_reserved_by(dashboard: Page, free_port):
    board = DashboardPage(dashboard)
    board.reserve_port(free_port)
    expect(board.port_row(free_port)).to_contain_text(settings.NTG_USER)
