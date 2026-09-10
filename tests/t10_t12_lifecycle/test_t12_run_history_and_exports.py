"""T12 — Run history table, export formats, delete a run, Reports badge.

One real run, reused for every T12 assertion rather than paying for
several activations. Confirmed by exploration:
- The run history row: `#1`/`latest` · Started At · Duration · Total
  Test Time · Avg Tx · Avg Rx · Loss % · Result (`pass`, lowercase DOM
  text, styled uppercase — same trap as elsewhere) · a `title` on the
  Result cell reading "loss-based default (no pass criteria set)" —
  still true, matches the open PASS-threshold question in project
  memory. Export buttons scope by their `title` attribute: "Download
  PDF report" / "Download Excel workbook (all sheets)" / "Download CSV"
  / "Download report JSON" / "Download all formats (PDF, XLSX, CSV,
  JSON) as a zip".
- The dashboard tile only shows a "Reports: N" badge once the testbed
  is fully deactivated (ports released) — while ACTIVE it shows a
  "Stats" button instead, even with saved runs. So the Reports-badge
  checks happen after releasing ports, reusing the same testbed.
- Delete run has `aria-label="Delete run"` — no confirm dialog observed
  for a single run's icon delete (unlike testbed/profile delete).
"""
import json

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
NAME = "T12-RunHistory"
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
def test_t12_run_history_exports_delete_and_reports_badge(
    dashboard: Page, clean_testbed, tmp_path
):
    page = dashboard

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
    hold.fill("10")
    hold.press("Tab")
    ramp_down.fill("5")
    ramp_down.press("Tab")

    page.get_by_role("button", name="Apply", exact=True).click()
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    page.wait_for_timeout(2000)

    # Wait for natural completion (ramp 5+10+5=20s).
    expect(page.get_by_text("LIVE · IDLE", exact=True)).to_be_visible(timeout=45000)

    # --- Run history row ---
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible()
    expect(run_row.get_by_text("pass", exact=True)).to_be_visible()
    cells = run_row.locator("td")
    expect(cells.nth(1)).not_to_have_text("")  # Started At
    expect(cells.nth(2)).not_to_have_text("")  # Duration
    expect(cells.nth(4)).to_contain_text("Gbps")  # Avg Tx
    expect(cells.nth(5)).to_contain_text("Gbps")  # Avg Rx
    expect(cells.nth(6)).to_contain_text("%")  # Loss %

    # --- Exports ---
    with page.expect_download(timeout=10000) as pdf_dl:
        run_row.locator('button[title="Download PDF report"]').click()
    pdf_path = tmp_path / pdf_dl.value.suggested_filename
    pdf_dl.value.save_as(str(pdf_path))
    assert pdf_path.stat().st_size > 0
    assert pdf_path.suffix == ".pdf"

    with page.expect_download(timeout=10000) as json_dl:
        run_row.locator('button[title="Download report JSON"]').click()
    json_path = tmp_path / json_dl.value.suggested_filename
    json_dl.value.save_as(str(json_path))
    report = json.loads(json_path.read_text())
    assert report, "expected the JSON report to have some top-level content"

    with page.expect_download(timeout=10000) as csv_dl:
        run_row.locator('button[title="Download CSV"]').click()
    assert csv_dl.value.suggested_filename.endswith(".csv")

    with page.expect_download(timeout=10000) as xlsx_dl:
        run_row.locator('button[title="Download Excel workbook (all sheets)"]').click()
    assert xlsx_dl.value.suggested_filename.endswith(".xlsx")

    with page.expect_download(timeout=10000) as zip_dl:
        run_row.locator(
            'button[title="Download all formats (PDF, XLSX, CSV, JSON) as a zip"]'
        ).click()
    assert zip_dl.value.suggested_filename.endswith(".zip")

    # --- Reports badge: only appears once the testbed is deactivated ---
    # Releasing the first port's reservation deactivates the whole
    # testbed (and both its ports) at once — guard each click on the
    # Release button still being present, same as `_release_ports`.
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    for port_label in PORTS:
        port_row = page.get_by_role("row", name=port_label)
        release_btn = port_row.get_by_role("button", name="Release")
        if release_btn.is_visible():
            release_btn.click()
            confirm = page.get_by_role("button", name="Deactivate & release")
            if confirm.is_visible():
                confirm.click()
            expect(port_row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)

    tile = _testbed_tile(page)
    reports_badge = tile.get_by_role("button", name="Reports:", exact=False)
    expect(reports_badge).to_contain_text("1")
    reports_badge.click()
    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible(timeout=10000)

    # --- Delete the run ---
    run_row.locator('button[aria-label="Delete run"]').click()
    confirm = page.get_by_role("button", name="Delete", exact=True)
    if confirm.is_visible():
        confirm.click()
    expect(page.locator("table.runs-table tbody tr")).to_have_count(0, timeout=10000)

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=10000)
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Reports:", exact=False)).to_have_count(0)
