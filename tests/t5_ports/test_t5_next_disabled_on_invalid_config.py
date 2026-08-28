"""T5 — Invalid Ports step config disables Next, with an explanatory tooltip.

The plan's known trigger is "bidirectional port with Peer Port = none".
Confirmed by exploration: with exactly two ports enabled, the app
auto-selects each as the other's default peer, so the invalid state has
to be forced by manually setting Port 1's Peer Port back to "— none —"
while it stays bidirectional. That state disables the "Next →" button,
which gets wrapped in a `<span data-tip="port 1 needs a peer port — or
the multisite checkbox to continue">` — the same data-tip tooltip
mechanism used by the icon-only card buttons elsewhere (see T4), not
rendered DOM text, so it has to be asserted via the attribute rather
than get_by_text(). Re-picking a peer re-enables Next and removes the
data-tip.

Note: no red ✕/error class was found on the step-1 tab badge itself in
this state (just `wiz-step active clickable`, no invalid/error class) —
the plan's "stepper shows red ✕" claim doesn't hold as literally
described on this app version. This test asserts the confirmed,
observable mechanism (Next disabled + tooltip) instead of the
unconfirmed one.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-NextInvalid-DeleteMe"


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
def test_t5_next_disabled_when_bidirectional_peer_is_none(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)

    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    peer1 = row1.locator("select").nth(1)
    next_btn = page.get_by_role("button", name="Next", exact=False)

    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    expect(peer1).to_have_value("2")  # auto-selected peer
    expect(next_btn).to_be_enabled()

    peer1.select_option(label="— none —")
    expect(next_btn).to_be_disabled()
    # The explanation is a data-tip attribute on the wrapping span (same
    # tooltip mechanism as the icon-only card buttons elsewhere in the
    # app), not rendered DOM text — get_by_text() can't see it, so assert
    # the attribute directly. The same explanation also shows up on the
    # later (still-unreached) step tabs, so scope to Next's own wrapper.
    next_tip = next_btn.locator("xpath=..")
    assert "needs a peer port" in (next_tip.get_attribute("data-tip") or "")

    peer1.select_option(label="Port 2")
    expect(next_btn).to_be_enabled()
    assert next_tip.get_attribute("data-tip") is None
