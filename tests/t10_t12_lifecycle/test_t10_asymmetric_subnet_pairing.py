"""T10 — exploratory: mismatched subnet mask widths across a single stream's
two ends.

The already-confirmed findings ("No client-side validation on Network
Configuration's IP or MAC fields" and "Declared numeric bounds aren't
enforced") both show the wizard accepting garbage values (malformed IPs,
out-of-range octets, out-of-bounds frame sizes) with no complaint. This test
probes a different, more subtle gap: not a malformed value on one side, but
two individually *valid* values that disagree with each other across the two
ends of the same conversation. Source (Port 3) is configured as
`10.0.20.1/25` (126 hosts) while destination (Port 4) is configured as
`10.0.20.2/28` (14 hosts) — both addresses sit in the same `10.0.20.0/24`
range, so this is deliberately NOT a "genuinely different subnet" test; the
only variable under test is the two sides declaring different mask widths
for what is otherwise one symmetric UDP stream. (CIDR options confirmed by
prior exploration to run `/25` through `/32` only, no `/24` — see
`test_t6_host_count_math.py`; `/25` and `/28` are two clearly different
widths from that range.)

This is genuinely exploratory — there's no pre-registered "correct" outcome.
Candidate results, roughly in order of how boring/interesting they'd be:
  1. Wizard accepts the mismatch silently (no validation, consistent with
     the already-known gap) AND the run activates, sends real non-zero
     Tx/Rx, and reports PASS. Boring-but-useful: shows the product tolerates
     asymmetric mask widths gracefully at the traffic layer, i.e. the mask
     width is cosmetic/host-count-display-only and doesn't feed anything
     that actually gates the conversation.
  2. Wizard accepts it, activation succeeds, but Rx is zero / traffic
     doesn't actually flow, or the result is a confusing/contradictory
     state (the VXLAN bug elsewhere in this suite is exactly this shape:
     "traffic-running": true next to "datapath-state": "IDLE"). That would
     be a genuine, new bug distinct from the known validation gaps.
  3. Activation itself fails, hangs, or crashes the page. Also a genuine
     bug, and grounds to stop immediately and report rather than iterate.

Whatever happens, this test does NOT get modified after the fact to force a
pass — a real product bug found here gets reported, not routed around.

Ports: 3 + 4 only (both confirmed clear of other users' work and clear of
the Port 5/6 link-down hardware issue on this box). Stateful: generates real
traffic.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-AsymCIDR"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
# Source (Port 3) side of the conversation.
SRC_IP = "10.0.20.1"
SRC_CIDR = "25"  # /25 — 126 hosts, the wide end
# Destination (Port 4) side of the conversation — same /24 range as SRC_IP,
# deliberately narrower mask.
DST_IP = "10.0.20.2"
DST_CIDR = "28"  # /28 — 14 hosts, the narrow end
# This app's own UI needs a short settling moment after several wizard
# actions (toggles, selects) or the next locator's actionability wait can
# time out — see feedback_codegen_replay_reliability memory. expect()
# assertions are used for the actual correctness checks; this is purely a
# settle buffer.
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=TESTBED_NAME)


def _delete_testbed_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        # Icon order confirmed via screenshot: [0]=download [1]=duplicate [2]=delete
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    # The test may fail mid-wizard/mid-activation, off the dashboard
    # entirely — get back to it first so the port rows below actually
    # exist. Prefer the SPA's own "← Dashboard" button when it's present.
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal that
        # blocks the plain click above from actually landing on the
        # dashboard.
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
def test_t10_asymmetric_subnet_pairing(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 3 and Port 4 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Create testbed ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 1 Gbps line rate ---
    # Always target the tile by name, never a positional index (see
    # feedback_codegen_replay_reliability memory / 2026-08-20 bug on the UDP
    # sibling test — a positional Edit click silently corrupted an
    # unrelated testbed once a 4th tile existed).
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill("1")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 4\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    # --- Wizard step 2: Network Configuration ---
    # The one deliberate variable under test: Port 3 (source) gets a /25
    # mask, Port 4 (destination) gets a /28 mask, while both IPs stay in the
    # same 10.0.20.0/24 range. Structurally identical to the UDP sibling
    # test's step 2 — only the literal IP/CIDR values differ.
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill(SRC_IP)
    _buffer(page)
    page.locator(".seg").first.select_option(SRC_CIDR)
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill(DST_IP)
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option(DST_CIDR)
    _buffer(page)
    # Dest IP fields — Port 4's dest = Port 3's source, Port 3's dest =
    # Port 4's source, keeping this a single symmetric conversation.
    page.get_by_role("textbox", name="auto").nth(2).fill(SRC_IP)
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill(DST_IP)
    _buffer(page)

    # --- Wizard step 3: Streams — UDP (default-highlighted protocol), 1500-byte frames ---
    # Reusing the UDP sibling test's stream config verbatim — protocol
    # choice isn't the variable under test here.
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("1500")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    # --- Wizard step 4: Traffic and Load Profile ---
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("10")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("50")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("10")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    # If the mismatched masks are going to cause a hard failure, this is
    # the first place it could show up (silently stuck on Apply forever,
    # per the known 502/name-length bug's symptom shape — ruled out here
    # since the name is short, but the UI-visible failure mode would look
    # the same for any other backend rejection). Give activation real room
    # — confirmed elsewhere that slow-but-working can look hung well past
    # 30s.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()

    # Clicking Start navigates into the Statistics view. Use the SPA's own
    # "← Dashboard" button rather than a hard nav — a forced reload mid
    # in-flight request has failed this suite before.
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Wait for the run to finish naturally — never race ahead of it ---
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify PASS, and that real (non-zero) traffic actually moved ---
    # A clean PASS on its own isn't enough evidence here: the VXLAN bug
    # elsewhere in this suite shows the product can report a run as
    # "started" while zero traffic actually flows. Read the run-history
    # row's Avg Tx / Avg Rx cells and assert they're actually non-zero
    # Gbps figures, not just present.
    tile.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)

    run_row = page.locator("table.runs-table tbody tr").first
    expect(run_row).to_be_visible()
    cells = run_row.locator("td")
    avg_tx_text = cells.nth(4).inner_text()
    avg_rx_text = cells.nth(5).inner_text()
    expect(cells.nth(4)).to_contain_text("Gbps")
    expect(cells.nth(5)).to_contain_text("Gbps")
    tx_match = re.search(r"[\d.]+", avg_tx_text)
    rx_match = re.search(r"[\d.]+", avg_rx_text)
    assert tx_match and float(tx_match.group()) > 0, (
        f"Avg Tx reported as {avg_tx_text!r} on an asymmetric /25↔/28 "
        "pairing — PASS badge but no evidence traffic actually sent."
    )
    assert rx_match and float(rx_match.group()) > 0, (
        f"Avg Rx reported as {avg_rx_text!r} on an asymmetric /25↔/28 "
        "pairing — PASS badge but no evidence traffic actually arrived."
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
