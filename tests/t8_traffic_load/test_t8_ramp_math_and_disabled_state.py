"""T8 — Load profile ramp: disabled-state text, and ramp-up+hold+ramp-down math.

Confirmed by exploration (5.0.9, 2026-10-11):
- The Load profile toggle is off by default and reads
  "Disabled | Runs until Manual Stop" (5.0.7: "Disabled — traffic runs at
  full rate"), with no ramp inputs shown.
- Enabling it ("Ramp enabled") reveals Ramp up / Hold time / Ramp down
  inputs (each with a sec/min unit select) and a line reading "Total run
  time = ramp-up + hold + ramp-down = <a> + <b> + <c> = <total>s", which
  recomputes live as the inputs change (10/60/10=80s -> 20/60/10=90s).
- NTG 5.0 removed 4.0's Iterations field, so this no longer covers it.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-RampMath"


@pytest.fixture
def editor(dashboard: Page):
    board, ed = DashboardPage(dashboard), TestbedEditorPage(dashboard)
    board.remove_testbed(NAME)
    board.create_testbed(NAME)
    board.open_editor(NAME)
    ed.enable_ports([1, 2])
    ed.add_stream("UDP")
    ed.open_step(4)
    yield ed
    board.remove_testbed(NAME)


@pytest.mark.hardware_free
def test_t8_ramp_disabled_by_default(dashboard: Page, editor):
    expect(editor.load_profile_checkbox()).not_to_be_checked()
    expect(dashboard.get_by_text("Disabled | Runs until Manual Stop")).to_be_visible()
    expect(editor.ramp_field("Ramp up")).to_have_count(0)


@pytest.mark.hardware_free
def test_t8_ramp_math_updates_total_run_time(dashboard: Page, editor):
    editor.set_load_profile_enabled(True)
    expect(dashboard.get_by_text("Ramp enabled")).to_be_visible()
    expect(editor.total_run_time()).to_contain_text("10 + 60 + 10 = 80s")

    ramp_up = editor.ramp_field("Ramp up")
    ramp_up.fill("20")
    ramp_up.press("Tab")
    expect(editor.total_run_time()).to_contain_text("20 + 60 + 10 = 90s")
