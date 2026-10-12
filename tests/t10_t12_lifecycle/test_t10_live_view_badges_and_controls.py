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

NTG 5.0 rewrite (2026-09-30): setup uses the shared conftest helpers and
starts via the editor's Start -> "Testbed is Inactive" -> Continue, which
lands on Statistics just like 4.0's post-Apply Start did. The live/idle
badges and every T11 control below are unchanged in 5.0.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import (
    add_stream,
    assert_activatable_name,
    create_testbed,
    enable_ports,
    go_to_dashboard,
    open_editor,
    remove_testbed,
    set_ramp,
    start_testbed,
    testbed_tile,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
NAME = "T10-LiveView"
assert_activatable_name(NAME)
PORTS = ["Port 1", "Port 2"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, NAME)
    yield
    remove_testbed(dashboard, NAME)


@pytest.mark.stateful
def test_t10_live_badges_and_t11_stats_controls(dashboard: Page, clean_testbed):
    page = dashboard
    testbeds_hdr = page.locator(".card-hdr").filter(has_text="Testbeds")
    before = re.search(r"(\d+) active", testbeds_hdr.inner_text())
    active_before = int(before.group(1)) if before else 0

    create_testbed(page, NAME)
    open_editor(page, NAME)
    enable_ports(page, PORTS, rate="1", unit="Gbps")
    add_stream(page, "UDP")
    set_ramp(page, up=5, hold=15, down=5)
    start_testbed(page)

    # --- Live: badges + dashboard active counter + non-zero per-port table ---
    expect(page.get_by_role("heading", name=re.compile(r"^Statistics"))).to_be_visible(timeout=15_000)
    expect(page.locator(".pill", has_text="active")).to_be_visible(timeout=15_000)
    # "LIVE" alone also matches the testbed name "T10-LiveView" — match the
    # badge's "LIVE ·" separator instead.
    expect(page.get_by_text("LIVE ·", exact=False)).to_be_visible(timeout=15_000)

    go_to_dashboard(page)
    expect(testbeds_hdr).to_contain_text(f"{active_before + 1} active")

    testbed_tile(page, NAME).get_by_role("button", name="Stats").click()
    per_port_heading = page.get_by_text("Per-Port Aggregate Statistics", exact=False)
    expect(per_port_heading).to_be_visible(timeout=15_000)
    # "Port 1" also matches the Stream Statistics table further down —
    # scope to the table right after this heading.
    per_port_table = per_port_heading.locator("xpath=following::table[1]")
    port1_row = per_port_table.get_by_role("row", name=re.compile(r"^Port 1\b"))
    row_text = ""
    for _ in range(30):
        row_text = port1_row.inner_text().replace("Port 1", "")
        if re.search(r"[1-9]", row_text):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(f"Port 1 row never showed nonzero traffic while running: {row_text!r}")

    # --- Natural completion: still ACTIVE, now IDLE ---
    expect(page.get_by_text("LIVE · IDLE", exact=True)).to_be_visible(timeout=45_000)
    expect(page.locator(".pill", has_text="active")).to_be_visible()

    # --- T11 stats view controls (only present while ACTIVE) ---
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
        # "bps" needs exact=True — it's a substring of "Gbps"/"Mbps".
        page.get_by_role("button", name=unit_name, exact=(unit_name == "bps")).click()
        expect(page.get_by_text("Throughput", exact=True).first).to_be_visible()

    page.get_by_role("button", name="Full").click()
    page.get_by_role("button", name="1.2M").click()
