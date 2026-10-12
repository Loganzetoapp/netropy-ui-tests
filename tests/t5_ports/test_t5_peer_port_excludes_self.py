"""T5 — Peer Port options exclude the port itself.

Confirmed by exploration: with only Port 1 enabled, its Peer Port select
offers only "— none —" (no other enabled port to pair with). Once Port 2
is also enabled, Port 1's Peer Port select gains a "Port 2" option (never
"Port 1"), and vice versa — the app auto-selects the sole other enabled
port as each side's default peer.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage

NAME = "T5-PeerPort-DeleteMe"


@pytest.mark.hardware_free
def test_t5_peer_port_options_exclude_self(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    peer1 = row1.locator("select").nth(1)
    peer2 = row2.locator("select").nth(1)

    row1.locator(".toggle .track").click()
    expect(peer1).to_be_enabled()
    assert peer1.locator("option").all_inner_texts() == ["— none —"]

    row2.locator(".toggle .track").click()
    expect(peer2).to_be_enabled()

    expect(peer1.locator("option")).to_have_count(2)
    peer1_options = peer1.locator("option").all_inner_texts()
    assert "Port 1" not in peer1_options
    assert "Port 2" in peer1_options

    peer2_options = peer2.locator("option").all_inner_texts()
    assert "Port 2" not in peer2_options
    assert "Port 1" in peer2_options

    # Auto-selected as each other's default peer once both are enabled.
    # Option values are the bare port number ("2"), not the "Port 2" label.
    expect(peer1).to_have_value("2")
    expect(peer2).to_have_value("1")
