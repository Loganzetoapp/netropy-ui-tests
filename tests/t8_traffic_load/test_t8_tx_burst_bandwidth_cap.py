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

NAME = "T8-TxBurst-DeleteMe"


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


def _create_and_open_streams(page: Page, name: str = NAME):
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
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    page.get_by_role("button", name="3 Streams", exact=False).click()
    expect(page.get_by_role("button", name="✚ Add Stream", exact=True)).to_be_visible(
        timeout=10000
    )


def _add_stream(page: Page):
    page.get_by_role("button", name="✚ Add Stream", exact=True).click()
    expect(page.get_by_role("button", name="Add stream", exact=True)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="Add stream", exact=True).click()


def _open_load_profile(page: Page):
    header = page.get_by_role("button", name="4 Traffic and Load Profile", exact=False)
    header.click()
    expect(header).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".pill", has_text="used")).to_be_visible(timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t8_tx_burst_clamps_to_declared_max(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _open_load_profile(page)

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
    _create_and_open_streams(page)
    _add_stream(page)
    _open_load_profile(page)

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
