"""T5 — Line Rate field validation: 0, negative, above max, non-numeric.

Confirmed by exploration (the field is a plain `<input type="number"
min="0" step="any">`, no `max` attribute at all):
- "0" and negative values ("-5") are both rejected the same way: the
  value types in fine, but blurring the field (Tab) clears it back to
  empty — there's a lower-bound-only validation on blur.
- A value above the per-port 10 Gbps ceiling ("15") is accepted verbatim
  with no visible error and no clamping and survives blur — there's no
  client-side upper-bound check at all, flagged as a real gap rather
  than something to route around.
- Non-numeric text can't even be typed into the field — Chrome's native
  `<input type="number">` blocks non-digit keystrokes outright, so
  there's no "invalid text was accepted/rejected" case to assert; this
  test instead confirms that behavior (Playwright's `.fill()` refuses to
  insert letters into a number input, and keyboard-typed letters are
  silently dropped).
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T5-LineRate-DeleteMe"


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


def _create_and_open_edit(page: Page, name: str = NAME):
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


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t5_line_rate_zero_clears_on_blur(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)
    row1 = page.locator("tr").nth(1)
    row1.locator(".toggle .track").click()

    rate_input = row1.locator('input[placeholder="line rate"]')
    expect(rate_input).to_be_enabled()
    rate_input.fill("0")
    rate_input.press("Tab")
    expect(rate_input).to_have_value("")


@pytest.mark.hardware_free
def test_t5_line_rate_negative_clears_on_blur(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)
    row1 = page.locator("tr").nth(1)
    row1.locator(".toggle .track").click()

    rate_input = row1.locator('input[placeholder="line rate"]')
    expect(rate_input).to_be_enabled()
    rate_input.fill("-5")
    rate_input.press("Tab")
    expect(rate_input).to_have_value("")


@pytest.mark.hardware_free
def test_t5_line_rate_no_client_side_upper_bound(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)
    row1 = page.locator("tr").nth(1)
    row1.locator(".toggle .track").click()

    rate_input = row1.locator('input[placeholder="line rate"]')
    expect(rate_input).to_be_enabled()
    assert rate_input.get_attribute("max") is None

    rate_input.fill("15")
    rate_input.press("Tab")
    expect(rate_input).to_have_value("15")


@pytest.mark.hardware_free
def test_t5_line_rate_rejects_non_numeric_keystrokes(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_edit(page)
    row1 = page.locator("tr").nth(1)
    row1.locator(".toggle .track").click()

    rate_input = row1.locator('input[placeholder="line rate"]')
    expect(rate_input).to_be_enabled()
    with pytest.raises(Exception):
        rate_input.fill("abc")
