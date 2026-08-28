"""T5 — Peer Port options exclude the port itself.

Confirmed by exploration: with only Port 1 enabled, its Peer Port select
offers only "— none —" (no other enabled port to pair with). Once Port 2
is also enabled, Port 1's Peer Port select gains a "Port 2" option (never
"Port 1"), and vice versa — the app auto-selects the sole other enabled
port as each side's default peer.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-PeerPort-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


def _cleanup_from_wherever(page: Page, name: str = NAME):
    if _tile(page, name).count() > 0:
        _delete_if_present(page, name)
        return
    delete_btn = page.get_by_role("button", name="Delete", exact=True)
    if delete_btn.count() > 0 and delete_btn.first.is_visible():
        delete_btn.first.click()
        page.locator("button.btn-danger", has_text="Delete").click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    _delete_if_present(page, name)


def _create_and_open_edit(page: Page, name: str = NAME):
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _tile(page, name)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t5_peer_port_options_exclude_self(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

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
