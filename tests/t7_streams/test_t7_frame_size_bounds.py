"""T7 — Frame size bounds: below 64, above the jumbo max (9216), non-numeric.

Unlike the wizard step-1 Line Rate field (T5) and step-2 IP/MAC fields
(T6), this field DOES declare real `min="64" max="9216"` attributes —
but, consistent with the app's general pattern, nothing enforces them:
values below 64 and above 9216 are both accepted verbatim with no error
and no clamping on blur. Documented as a gap, not routed around.
Non-numeric text can't be typed at all (native `<input type="number">`
behavior, same as T5/T6).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-FrameSizeBounds-DeleteMe"


@pytest.mark.hardware_free
def test_t7_frame_size_below_64_accepted_without_clamping(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    frame_input = TestbedEditorPage(page).stream_rows().first.locator("td:nth-child(5) input")

    assert frame_input.get_attribute("min") == "64"
    frame_input.fill("32")
    frame_input.press("Tab")
    expect(frame_input).to_have_value("32")


@pytest.mark.hardware_free
def test_t7_frame_size_above_9216_accepted_without_clamping(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    frame_input = TestbedEditorPage(page).stream_rows().first.locator("td:nth-child(5) input")

    assert frame_input.get_attribute("max") == "9216"
    frame_input.fill("50000")
    frame_input.press("Tab")
    expect(frame_input).to_have_value("50000")


@pytest.mark.hardware_free
def test_t7_frame_size_rejects_non_numeric_keystrokes(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    frame_input = TestbedEditorPage(page).stream_rows().first.locator("td:nth-child(5) input")

    with pytest.raises(Exception):
        frame_input.fill("abc")
