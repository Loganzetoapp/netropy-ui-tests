"""T8 — Load profile ramp: disabled-state text, and ramp-up+hold+ramp-down math.

Confirmed by exploration:
- Ramp disabled by default (`Ramp enabled` toggle off), with the
  replacement-state text "Disabled — traffic runs at full rate" — not
  literally "constant load" as the plan phrased it, but the same idea.
- Enabling it reveals Ramp up / Hold time / Ramp down inputs (each with
  a sec/min unit `<select>`) and a line reading "Total run time =
  ramp-up + hold + ramp-down = <a> + <b> + <c> = <total>s", which
  recomputes live as the inputs change (10/60/10=80s -> 20/60/10=90s).
- Iterations > 1 appends "· ×N iterations" to that same line rather than
  pre-multiplying the shown total.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T8-RampMath-DeleteMe"


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
def test_t8_ramp_disabled_by_default(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _open_load_profile(page)

    expect(page.get_by_text("Disabled — traffic runs at full rate")).to_be_visible()
    expect(page.locator(".fc-combo")).to_have_count(0)


@pytest.mark.hardware_free
def test_t8_ramp_math_updates_total_run_time(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _open_load_profile(page)

    ramp_row = page.locator("div", has_text="Disabled — traffic runs at full rate").last
    ramp_row.locator(".toggle .track").click()

    total_line = page.locator("text=/Total run time/")
    expect(total_line).to_contain_text("10 + 60 + 10 = 80s")

    ramp_up = page.locator(".fg", has_text="Ramp up").locator('input[type="number"]')
    ramp_up.fill("20")
    ramp_up.press("Tab")
    expect(total_line).to_contain_text("20 + 60 + 10 = 90s")

    iterations = page.locator(
        'div[data-tip="How many times the ramp cycle repeats"] input'
    )
    iterations.fill("3")
    iterations.press("Tab")
    expect(total_line).to_contain_text("×3 iterations")
