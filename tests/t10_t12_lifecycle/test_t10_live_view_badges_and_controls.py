"""T10 (live badges/KPIs/dashboard-active) + T11 (stats view controls).

One real run covers both plan areas rather than paying for two separate
activations. Confirmed by exploration:
- While a run is live, the Statistics page header shows a `active` pill
  (lowercase in the DOM, uppercase via CSS — same trap as PASS/FAIL) and
  a plain-text "LIVE · <elapsed>" badge (e.g. "LIVE · 0:04"); once the
  run finishes naturally the elapsed clock is replaced with "LIVE ·
  IDLE" — the testbed stays ACTIVE, it just isn't transmitting.
- The Scope/Signal/metric-tabs/chart controls only exist while the
  testbed is ACTIVE (live or idle-after-a-run) — once fully deactivated
  the whole section is replaced by "Testbed not active." So this test
  deliberately checks those controls *before* releasing the ports.
- The dashboard's Testbeds card header text ("N saved · M active")
  increments while a run is live.
- Per-Port Aggregate Statistics shows non-zero current Tx/Rx while
  running (not just at the end).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
NAME = "T10-LiveView"
assert_activatable_name(NAME)
PORTS = ["Port 1", "Port 2"]


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=NAME)


def _delete_testbed_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        page.wait_for_timeout(400)
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        release_btn = row.get_by_role("button", name="Release")
        if release_btn.is_visible():
            release_btn.click()
            confirm = page.get_by_role("button", name="Deactivate & release")
            if confirm.is_visible():
                confirm.click()
            expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)


@pytest.fixture
def clean_testbed(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    yield
    _release_ports(dashboard)
    _delete_testbed_if_present(dashboard)


@pytest.mark.stateful
def test_t10_live_badges_and_t11_stats_controls(dashboard: Page, clean_testbed):
    page = dashboard

    # Baseline captured up front, on the dashboard, before this test's own
    # testbed exists — the box is shared, so this asserts the count went
    # up by one for *this* run rather than assuming a literal "1 active"
    # (someone else's testbed could also be active at the same time).
    testbeds_hdr = page.locator(".card-hdr").filter(has_text="Testbeds")
    active_count_pattern = re.compile(r"(\d+) active")
    before_match = active_count_pattern.search(testbeds_hdr.inner_text())
    active_before = int(before_match.group(1)) if before_match else 0

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = _testbed_tile(page)
    expect(tile).to_have_count(1, timeout=10000)
    tile.get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports", exact=False).first).to_be_visible(
        timeout=15000
    )
    row1 = page.locator("tr").nth(1)
    row2 = page.locator("tr").nth(2)
    row1.locator(".toggle .track").click()
    row2.locator(".toggle .track").click()
    for row in (row1, row2):
        rate_field = row.locator('input[placeholder="line rate"]')
        rate_field.fill("1")
        rate_field.press("Tab")

    page.get_by_role("button", name="3 Streams", exact=False).click()
    expect(page.get_by_role("button", name="✚ Add Stream", exact=True)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="✚ Add Stream", exact=True).click()
    expect(page.get_by_role("button", name="ICMP", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="ICMP", exact=True).click()
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()

    page.get_by_role("button", name="4 Traffic and Load Profile", exact=False).click()
    expect(page.locator(".pill", has_text="used")).to_be_visible(timeout=10000)
    ramp_row = page.locator("div", has_text="Disabled — traffic runs at full rate").last
    ramp_row.locator(".toggle .track").click()
    ramp_up = page.locator(".fg", has_text="Ramp up").locator('input[type="number"]')
    hold = page.locator(".fg", has_text="Hold time").locator('input[type="number"]')
    ramp_down = page.locator(".fg", has_text="Ramp down").locator('input[type="number"]')
    ramp_up.fill("5")
    ramp_up.press("Tab")
    hold.fill("15")
    hold.press("Tab")
    ramp_down.fill("5")
    ramp_down.press("Tab")

    page.get_by_role("button", name="Apply", exact=True).click()
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    # Clicking Start navigates into the Statistics view — not instant;
    # give the SPA a moment before asserting on that page's content
    # (same pattern as the other lifecycle tests' post-Start buffer).
    page.wait_for_timeout(2000)

    # --- Live: badges + dashboard active counter + non-zero per-port table ---
    expect(page.locator(".pill", has_text="active")).to_be_visible(timeout=15000)
    # "LIVE" alone (fuzzy/case-insensitive) also matches the testbed's own
    # name "T10-LiveView" — match the badge's distinctive "LIVE ·"
    # separator instead.
    expect(page.get_by_text("LIVE ·", exact=False)).to_be_visible(timeout=15000)

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    expect(testbeds_hdr).to_contain_text(f"{active_before + 1} active")

    tile = _testbed_tile(page)
    tile.get_by_role("button", name="Stats").click()
    per_port_heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(per_port_heading).to_be_visible(timeout=15000)
    # "Port 1" also matches a row in the separate Stream Statistics table
    # further down — scope to the table right after this heading.
    per_port_table = per_port_heading.locator("xpath=following::table[1]")
    port1_row = per_port_table.get_by_role("row", name="Port 1", exact=False)
    # Non-zero Tx/Rx while running. Checked by stripping the "Port 1"
    # label out of the row's text and looking for a remaining nonzero
    # digit, rather than guessing a specific `td` index — the exact
    # column order of Tx Rate/Rx Rate/Tx pps/Rx pps/Dropped Frames
    # wasn't confirmed, and "Dropped Frames" legitimately reads 0.
    # Hand-rolled retry (not expect()) since the check isn't a single
    # locator assertion.
    for _ in range(30):
        row_text = port1_row.inner_text().replace("Port 1", "")
        if re.search(r"[1-9]", row_text):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(
            f"Port 1 row never showed nonzero traffic while running: {row_text!r}"
        )

    # --- Wait for natural completion (still ACTIVE, now IDLE) ---
    expect(page.get_by_text("LIVE · IDLE", exact=True)).to_be_visible(timeout=45000)
    expect(page.locator(".pill", has_text="active")).to_be_visible()

    # --- T11 stats view controls (only present while ACTIVE) ---
    # Not exact=True: several of these buttons carry a data-tip
    # attribute directly, which — as found repeatedly in T7/T8 — throws
    # off Playwright's exact accessible-name match even though the
    # visible text and innerText agree; the fuzzy default is already
    # unambiguous for each of these labels on this page.
    for tab_name in ["Packet Rate", "Latency", "Frame Loss", "Jitter", "Throughput"]:
        page.get_by_role("button", name=tab_name).click()
        expect(page.get_by_text(tab_name, exact=True).first).to_be_visible()

    page.get_by_role("button", name="Per Stream").click()
    page.get_by_role("button", name="Aggregate").click()

    for scope_name in ["Average", "Port 1", "Port 2", "All Ports"]:
        page.get_by_role("button", name=scope_name).click()

    for signal_name in ["Tx", "Rx", "Both"]:
        page.get_by_role("button", name=signal_name).click()

    for unit_name in ["Gbps", "Mbps", "bps", "Auto"]:
        # "bps" needs exact=True — it's a substring of "Gbps"/"Mbps" and
        # would otherwise match 3 buttons instead of 1.
        page.get_by_role("button", name=unit_name, exact=(unit_name == "bps")).click()
        expect(page.get_by_text("Throughput", exact=True).first).to_be_visible()

    page.get_by_role("button", name="Full").click()
    page.get_by_role("button", name="1.2M").click()
