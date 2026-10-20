"""T8 — TX burst and Bandwidth cap fields.

Confirmed by exploration:
- TX burst (packets) has real `min="1" max="32"` attributes AND, unlike
  almost every other numeric field tested in this suite (Line Rate,
  IP/MAC, Frame size), actually enforces its max on blur: typing "100"
  gets clamped down to "32". Placeholder reads "1 (blank = device
  default, 32)" — blank means device default.
- Bandwidth cap (Gbps) is currently disabled entirely, wrapped in a
  `data-tip="Testbed-wide bandwidth cap is not configurable yet"` — a
  known not-yet-implemented field, same as the "Connectivity
  diagnostics" section below it (WORK IN PROGRESS). Not exercised
  further; just confirmed disabled with its explanatory tooltip rather
  than silently treated as broken.
"""
import pytest
from playwright.sync_api import Page, expect

from pages import DashboardPage, TestbedEditorPage

NAME = "T8-TxBurst-DeleteMe"


@pytest.mark.hardware_free
def test_t8_tx_burst_clamps_to_declared_max(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    tx_burst = page.locator('input[max="32"]')
    assert tx_burst.get_attribute("min") == "1"
    expect(tx_burst).to_have_attribute(
        "placeholder", "1 (blank = device default, 32)"
    )

    tx_burst.fill("100")
    tx_burst.press("Tab")
    expect(tx_burst).to_have_value("32")


@pytest.mark.hardware_free
def test_t8_bandwidth_cap_not_yet_configurable(dashboard: Page, clean_up):
    page = dashboard
    DashboardPage(page).open_draft(NAME, ports=(1, 2), step=3)
    TestbedEditorPage(page).add_stream("UDP")
    TestbedEditorPage(page).open_load_profile()

    # Scoped via the data-tip wrapper, not get_by_placeholder("line rate")
    # — the Ports roster table's per-port Line Rate inputs share that
    # exact placeholder and stay mounted alongside step 4 (the Ports
    # panel is the one step that's always pinned open).
    wrapper = page.locator(
        '[data-tip="Testbed-wide bandwidth cap is not configurable yet"]'
    )
    expect(wrapper).to_have_count(1)
    bandwidth_cap = wrapper.locator('input[placeholder="line rate"]')
    expect(bandwidth_cap).to_be_disabled()
