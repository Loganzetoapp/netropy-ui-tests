"""T7 — "Distribute across ports" bulk-assigns each stream's Interface Port ID.

Confirmed by exploration these are one-shot bulk-apply actions (no
persistent selected/active state), same pattern as the network-config
🔗 auto-fill buttons in T6 — not a toggle. With 3 streams across 2 ports:
- All Ports: every stream's Interface Port ID is "all"
- Alternate (round-robin): 1, 2, 1
- Sequence (contiguous blocks): 1, 1, 2
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T7-Distribute-DeleteMe"


@pytest.mark.hardware_free
def test_t7_distribute_across_ports_alternate_vs_sequence(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    for _ in range(3):
        TestbedEditorPage(page).add_stream("UDP")
    rows = TestbedEditorPage(page).stream_rows()
    expect(rows).to_have_count(3)
    port_id_selects = [rows.nth(i).locator("select").first for i in range(3)]

    for sel in port_id_selects:
        expect(sel).to_have_value("all")

    # Not get_by_role(..., exact=True): the button's own accessible name
    # computation ends up not exactly "Alternate"/"Sequence"/"All Ports"
    # (likely folding in its data-tip description) even though the
    # visible text and innerText are exactly that — exact=True finds 0
    # matches while the fuzzy default finds exactly 1, unambiguously.
    page.get_by_role("button", name="Sequence").click()
    expect(port_id_selects[0]).to_have_value("1")
    expect(port_id_selects[1]).to_have_value("1")
    expect(port_id_selects[2]).to_have_value("2")

    page.get_by_role("button", name="Alternate").click()
    expect(port_id_selects[0]).to_have_value("1")
    expect(port_id_selects[1]).to_have_value("2")
    expect(port_id_selects[2]).to_have_value("1")

    page.get_by_role("button", name="All Ports").click()
    for sel in port_id_selects:
        expect(sel).to_have_value("all")
