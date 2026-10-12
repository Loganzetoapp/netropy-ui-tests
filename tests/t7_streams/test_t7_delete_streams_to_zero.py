"""T7 — Deleting all streams flags the step invalid; Start disabled.

Confirmed by exploration (5.0.9, 2026-10-11): the stepper tab for step 3
reads "3 Streams 0 streams" / "… 1 stream", and the editor's Start button
(5.0's rename of 4.0's Apply: save + activate + run, same gating) is
disabled with no streams. The step's hint text is now static ("The
traffic flows this testbed sends. At least one is needed to activate"), so
the count is read from the tab. The Start click never enters this test.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-DelStreams"


@pytest.fixture
def editor(dashboard: Page):
    board, ed = DashboardPage(dashboard), TestbedEditorPage(dashboard)
    board.remove_testbed(NAME)
    board.create_testbed(NAME)
    board.open_editor(NAME)
    ed.enable_ports([1, 2])
    ed.open_step(3)
    yield ed
    board.remove_testbed(NAME)


@pytest.mark.hardware_free
def test_t7_deleting_all_streams_disables_apply(dashboard: Page, editor):
    tab = editor.step_tab(3)
    expect(tab).to_contain_text("0 streams")
    expect(editor.start_button).to_be_disabled()

    editor.add_stream("UDP")
    expect(tab).to_contain_text("1 stream")

    rows = editor.stream_rows()
    rows.first.locator('span[data-tip="Delete stream"] button').click()
    expect(rows).to_have_count(0)
    expect(tab).to_contain_text("0 streams")
    expect(editor.start_button).to_be_disabled()
