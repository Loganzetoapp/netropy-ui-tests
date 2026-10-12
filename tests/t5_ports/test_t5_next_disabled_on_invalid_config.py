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

from pages import DashboardPage

NAME = "T5-NextInvalid-DeleteMe"


@pytest.mark.hardware_free
def test_t5_next_disabled_when_bidirectional_peer_is_none(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME)

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
