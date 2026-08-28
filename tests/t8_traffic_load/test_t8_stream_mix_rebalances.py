"""T8 — Wizard step 4 (Traffic and Load Profile): stream mix auto-rebalances.

Confirmed by exploration: adding streams auto-splits the mix evenly
(1 stream = 100%, 2 = 50/50, 3 = 33.3/33.3/33.3), and editing one
stream's inline share auto-rebalances the others to keep the total at
100% (set stream 1 to 70% with 2 streams -> stream 2 becomes 30%
automatically). USED/REMAINING are `<span class="pill">` elements whose
DOM text is lowercase ("used 100%"/"remaining 0%") though displayed
uppercase via CSS — same trap as other badges in this app.
"""
import pytest
from playwright.sync_api import Page, expect

NAME = "T8-MixRebalance-DeleteMe"


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


def _stream_share_button(page: Page, stream_name: str):
    return page.locator(f'div:has(> span:text-is("{stream_name}"))').locator(
        'button[title="Click to edit share"]'
    )


@pytest.fixture
def clean_up(dashboard: Page):
    _cleanup_from_wherever(dashboard)
    yield
    _cleanup_from_wherever(dashboard)


@pytest.mark.hardware_free
def test_t8_stream_mix_splits_evenly_on_add(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    # Add both streams up front, on the Streams step, before ever
    # navigating to step 4 — the wizard's accordion only keeps one
    # non-Ports panel expanded at a time and toggles (not just opens) on
    # click, so hopping back and forth between steps is fragile; adding
    # everything needed first and opening Load Profile once avoids it.
    _add_stream(page)
    _add_stream(page)
    _open_load_profile(page)

    expect(_stream_share_button(page, "udp-1")).to_have_text("50%")
    expect(_stream_share_button(page, "udp-2")).to_have_text("50%")

    used_pill = page.locator(".pill", has_text="used")
    remaining_pill = page.locator(".pill", has_text="remaining")
    expect(used_pill).to_have_text("used 100%")
    expect(remaining_pill).to_have_text("remaining 0%")


@pytest.mark.hardware_free
def test_t8_editing_one_share_rebalances_the_other(dashboard: Page, clean_up):
    page = dashboard
    _create_and_open_streams(page)
    _add_stream(page)
    _add_stream(page)
    _open_load_profile(page)

    share_1 = _stream_share_button(page, "udp-1")
    share_1.click()
    inp = page.locator('div:has(> span:text-is("udp-1"))').locator(
        'input[type="number"]'
    )
    inp.fill("70")
    inp.press("Tab")

    expect(_stream_share_button(page, "udp-1")).to_have_text("70%")
    expect(_stream_share_button(page, "udp-2")).to_have_text("30%")
    expect(page.locator(".pill", has_text="used")).to_have_text("used 100%")
