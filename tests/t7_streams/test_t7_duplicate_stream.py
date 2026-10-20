"""T7 — Duplicate (clone) a stream: distinct copy, name increments.

Confirmed by exploration: the clone icon (data-tip "Clone stream")
creates an immediate copy — no confirm dialog, unlike Clone Testbed in
T4 — named "<original>-copy" (same "-copy" suffix convention as T4's
testbed clone).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-DuplicateStream-DeleteMe"


@pytest.mark.hardware_free
def test_t7_clone_stream_creates_distinct_named_copy(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    rows = TestbedEditorPage(page).stream_rows()

    TestbedEditorPage(page).add_stream("UDP")
    expect(rows).to_have_count(1)

    rows.first.locator('span[data-tip="Clone stream"] button').click()
    expect(rows).to_have_count(2)

    names = [rows.nth(i).locator("td").first.locator("input").input_value() for i in range(2)]
    assert names == ["udp-1", "udp-1-copy"]
