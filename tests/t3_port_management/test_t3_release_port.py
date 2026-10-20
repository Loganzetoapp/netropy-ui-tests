"""T3 port management — release a port returns it to Unreserved (4.0: "Available").

Port state is global on shared hardware: this test must release what it
reserves, even on failure, so the fixture teardown always attempts a
release.

On pages/ (2026-10-11).
"""
import pytest
from playwright.sync_api import Page

from pages import DashboardPage


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
def test_t3_release_port_returns_to_available(dashboard: Page, free_port):
    board = DashboardPage(dashboard)
    board.reserve_port(free_port)
    board.release_port(free_port)
