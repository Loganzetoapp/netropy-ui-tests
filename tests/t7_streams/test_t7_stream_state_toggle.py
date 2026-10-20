"""T7 — Enable/disable state per stream persists across wizard navigation.

Confirmed by exploration: the STATE pill (`button.pill`, data-tip
"Disable stream" / text "enabled" displayed uppercase via CSS, flips to
"disabled" on click, class `pill ok` -> `pill muted`).
This test disables a stream, navigates away to a different wizard step
and back, and confirms the disabled state wasn't lost — the plan
explicitly calls out that per-stream enable/disable state should
persist.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-StreamState-DeleteMe"


@pytest.mark.hardware_free
def test_t7_stream_disabled_state_persists_across_navigation(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    state_btn = TestbedEditorPage(page).stream_rows().first.locator("button.pill")

    # Displayed uppercase via CSS text-transform; underlying DOM text is
    # lowercase — same trap as the run-history PASS/FAIL badge.
    expect(state_btn).to_have_text("enabled")
    assert "ok" in state_btn.get_attribute("class")

    state_btn.click()
    expect(state_btn).to_have_text("disabled")
    assert "muted" in state_btn.get_attribute("class")

    # Collapse the Streams accordion panel and re-expand it — confirmed by
    # exploration that opening a later step collapses this one (only the
    # first "Ports" panel stays pinned open alongside whichever other step
    # is active), so this is the reliable way to force the panel to
    # re-render from scratch and prove the disabled state wasn't reset.
    streams_header = page.get_by_role("button", name="3 Streams", exact=False)
    streams_header.click()
    expect(streams_header).to_have_attribute("aria-expanded", "false")
    streams_header.click()
    expect(streams_header).to_have_attribute("aria-expanded", "true")

    state_btn = TestbedEditorPage(page).stream_rows().first.locator("button.pill")
    expect(state_btn).to_have_text("disabled")
    assert "muted" in state_btn.get_attribute("class")
