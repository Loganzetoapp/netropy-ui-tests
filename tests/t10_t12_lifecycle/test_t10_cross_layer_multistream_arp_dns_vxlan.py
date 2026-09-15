"""T10/T12 combined lifecycle test — cross-layer multi-stream (ARP + DNS +
VXLAN) on one testbed.

Genuinely exploratory. Every existing lifecycle test either exercises one
protocol per testbed, or — in the closest sibling,
`test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps.py` — combines two
streams that are both ordinary IP traffic (TCP + ICMP, same
Ethernet/IPv4 layer shape, differing only above IPv4). Nobody has yet
asked the wizard to combine streams from three genuinely different
protocol *categories* in one traffic mix on one wire:

- **ARP** (Layer 2, no IP at all) — picker text "Address resolution
  frames", layer stack Ethernet -> Payload only, no default ports. See
  `test_t10_t12_lifecycle_arp_10mbps_64b.py`'s protocol research.
- **DNS** (Application, UDP) — picker text "Name lookups, UDP port 53",
  layer stack Ethernet -> IPv4 -> UDP -> Payload, default ports
  2048 -> 53. Not its own layer: the resulting stream's chips read UDP,
  not DNS. See `test_t10_t12_lifecycle_dns_200mbps_128b.py`.
- **VXLAN** (Tunnel, encapsulated) — picker text "Encapsulated inner
  stream, UDP 4789", layer stack Ethernet -> IPv4 -> UDP -> VXLAN ->
  Payload, default ports 2048 -> 4789. See
  `test_t10_t12_lifecycle_vxlan_4gbps_1500b.py`.

Questions this test is actually hunting answers to, not assuming:
1. Does the "Add Stream" wizard even let three streams from three
   different layer categories coexist on one testbed without erroring?
2. Does Apply ("Save & activate") succeed for a mix this heterogeneous?
3. Once live, does the Statistics page's Aggregate vs Per Stream toggle
   and Stream Statistics table correctly render all three streams —
   distinct rows, sane (non-NaN, non-duplicate) numbers per stream — or
   does mixing categories like this confuse whatever assumes a uniform
   stream shape?
4. Does the run reach a correct PASS/FAIL, or does something about this
   mix break the evaluation?

Rate design: this is one traffic mix on one wire, so the combined total
needs to stay modest even though the single-protocol siblings each ran
their own protocol considerably higher in isolation (ARP 10 Mbps, DNS
200 Mbps, VXLAN 4 Gbps as standalone tests). Rather than fight the
wizard's stream-mix share editor (three-way share rebalancing on
editing one field is undocumented behavior — see T8's rebalance tests,
which only demonstrate the two-stream case) and risk a selector/timing
bug of my own in a one-shot exploratory run, this reuses the same
approach as the TCP+ICMP multistream sibling: one combined port Line
Rate, left at the wizard's own even 3-way default split (confirmed
elsewhere to be ~33/33/34%) rather than hand-tuning per-stream shares.
1 Gbps combined (~330 Mbps per stream once split) is comfortably under
the port's line rate, in DNS's own standalone ballpark, well above
ARP's standalone rate (real ARP is bursty/low-volume, but the wizard
has no way to weight one stream near-zero without also touching the
others), and a steep scale-down from VXLAN's standalone 4 Gbps as asked
for combined-mix reasonableness. Frame sizes are kept protocol-realistic
per stream (ARP 64B / DNS 128B / VXLAN 1500B), matching each one's own
standalone sibling test exactly, since frame size is set per-stream
regardless of the shared rate.

Creates a Traffic Engine testbed on Port 3 + Port 4, adds ARP, DNS, and
VXLAN streams to the same testbed, activates it, waits for the run to
finish naturally, and checks the Statistics page's per-stream rendering
before asserting PASS/FAIL — then cleans up (release ports, delete
testbed).

Port constraint: Port 3 + Port 4 ONLY for this test — Port 1/2 are
reserved by other real users on this shared box, Port 5/6 has the
known recurring link-down issue, Port 7/8 are unconfirmed/flagged risky
in prior test comments (see netropy-ui-findings.md).

Stateful: generates real traffic on shared hardware.

Selector note: same caveats as every sibling — several wizard controls
have no accessible name/role/data-testid and fall back to CSS position
(`.fc`, `.seg`, `nth-child`).

--- Findings from the one-shot exploratory run (2026-09-15) ---
Ran once, on Port 3 + Port 4, per this test's own port constraint.

**The wizard itself handled the cross-layer combination fine.** Adding
ARP, then DNS, then VXLAN to the same testbed produced no error at any
point — each Add Stream completed normally, and all three layer chips
(Ethernet / UDP / VXLAN) were confirmed present together after the third
add, same as the TCP+ICMP sibling's two-stream case. Apply ("Save &
activate on the unit") also succeeded: the Deactivate button appeared
well inside its timeout, so activation itself is not where this breaks.

**Where it broke: the same "Start doesn't actually begin traffic" bug
already documented for standalone VXLAN, now reproduced in this 3-stream
cross-layer mix.** After clicking Start, the dashboard tile's own Stop
button appeared and then disappeared within the wait window — i.e. the
tile believed a run started and finished normally. But navigating into
Statistics via the tile's "Stats" button afterward showed the run had
never actually gone live at all: the page's own live-run status still
read "Ready to start traffic — Ports are armed and idle. Start traffic
to begin collecting live statistics." with its own separate "Start
traffic" button, while the header simultaneously showed the testbed as
"active LIVE · IDLE". This is the same self-contradictory pattern
netropy-ui-findings.md documents for the standalone VXLAN case
(`POST .../start?wait=15` returning `200` with `"traffic-running": true`
alongside `"datapath-state": "IDLE"` in the same body) — here visible as
two different parts of the UI (the dashboard tile vs. the Statistics
page) disagreeing about whether the run ever happened. `pytest`'s final
assertion (`expect(... get_by_text("pass"))`) failed because there was
no PASS/FAIL to find — the run never produced a result at all.

Consequence: the exploratory questions about the Statistics page's
per-stream rendering (Aggregate vs Per Stream toggle, Stream Statistics
table showing all three protocols without NaN/dropped rows) couldn't
actually be exercised this run — the page never left its pre-run empty
state, so this test's own `per_stream_toggle` check silently no-opped
both times it ran (right after Start, and again via Stats after the
tile's Stop button vanished) because that toggle was never visible to
click. That part of this test remains unanswered, not passing.

**New information this adds to the known bug:** previously this looked
confined to a standalone single-VXLAN-stream testbed (2 of 3 solo
attempts). This run shows the same failure mode occurs at least once
when VXLAN is mixed with ARP and DNS in the same testbed too, rather
than being purely a VXLAN-in-isolation quirk — consistent with, and
extending, the existing intermittent/backend-state-confusion theory
rather than pointing at anything specific to the cross-layer combination
itself (the wizard, addressing, and stream-add flow all worked cleanly;
only Start's backend state handling did not).

Per this repo's workflow rule, this failure was not worked around: the
test's assertions were left exactly as they are (a real, informative
FAIL), only this findings section was written up after the fact.
Hardware was left clean regardless — Port 3 and Port 4 both returned to
Available and the T10-XLayer testbed was deleted by this test's own
teardown (confirmed directly on the dashboard after the run).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-XLayer"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]
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
    # exist. Prefer the SPA's own "← Dashboard" button when it's present
    # (a hard goto() right after an in-flight activate call can itself
    # time out / crash teardown).
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal (Discard
        # / Save & close / Keep editing) that blocks the plain click above
        # from actually landing on the dashboard.
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
def test_t10_cross_layer_multistream_arp_dns_vxlan(dashboard: Page, clean_testbed):
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

    # --- Wizard step 1: Ports — enable Port 3 & Port 4, 1 Gbps combined
    # line rate (see docstring for the combined-rate reasoning) ---
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
    # Two of the three streams (DNS, VXLAN) are IP-based and need real
    # addressing; ARP has no IP layer, but per the ARP sibling's research
    # this form is generic to the testbed (not stream-aware) and renders
    # regardless — configuring it properly serves the two streams that
    # actually use it, and is harmless/ignored for the ARP one.
    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.13.1")
    _buffer(page)
    page.locator(".seg").first.select_option("27")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.13.2")
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("27")
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.13.1")
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill("10.0.13.2")
    _buffer(page)

    # --- Wizard step 3: Streams — ARP + DNS + VXLAN, three streams, three
    # genuinely different protocol categories, on one testbed ---
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)

    # Stream 1: ARP, 64-byte (Ethernet minimum) frames — Layer 2, no IP.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="ARP", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="Ethernet Edit Ethernet").first).to_be_visible()
    frame_size_inputs = page.locator("td:nth-child(5) > .fc")
    expect(frame_size_inputs).to_have_count(1)
    frame_size_inputs.first.fill("64")
    _buffer(page)
    frame_size_inputs.first.press("Enter")
    _buffer(page)

    # Stream 2: DNS, 128-byte frames — Application/UDP, added on top of ARP.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="DNS", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size_inputs = page.locator("td:nth-child(5) > .fc")
    expect(frame_size_inputs).to_have_count(2)
    frame_size_inputs.nth(1).fill("128")
    _buffer(page)
    frame_size_inputs.nth(1).press("Enter")
    _buffer(page)

    # Stream 3: VXLAN, 1500-byte frames — Tunnel/encapsulated, added on
    # top of ARP + DNS.
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    page.get_by_role("button", name="VXLAN", exact=True).click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="VXLAN Edit VXLAN").first).to_be_visible()
    frame_size_inputs = page.locator("td:nth-child(5) > .fc")
    expect(frame_size_inputs).to_have_count(3)
    frame_size_inputs.nth(2).fill("1500")
    _buffer(page)
    frame_size_inputs.nth(2).press("Enter")
    _buffer(page)

    # All three streams still present together — confirms adding stream 3
    # didn't silently replace or drop either of the first two.
    expect(page.get_by_role("button", name="Ethernet Edit Ethernet").first).to_be_visible()
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    expect(page.get_by_role("button", name="VXLAN Edit VXLAN").first).to_be_visible()

    # --- Wizard step 4: Traffic and Load Profile ---
    # 4/20/4 = 28s ramp — distinct from every other sibling's ramp. Stream
    # mix left at the wizard's own even 3-way default split (see docstring
    # for why this test doesn't hand-tune per-stream shares).
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        # Toggle state wasn't what we assumed — click again to reach the
        # ramp-enabled state that actually exposes the input fields below.
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("4")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("20")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("4")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    # "Apply" ("Save & activate on the unit") swaps the whole edit-view
    # action bar from Delete/Save/Apply to an active-testbed bar with
    # Delete/Deactivate/Stats/Save/Start — this doesn't happen instantly.
    # The activate call itself carries a `?wait=15` server-side contract
    # and can legitimately take longer than 30s plus UI lag to resolve.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()

    # Clicking Start (from inside the wizard's post-Apply action bar)
    # navigates into the Statistics view. Check the live Statistics page
    # itself before heading back to the dashboard — this is the actual
    # cross-layer question this test exists to answer: does the page
    # render all three streams correctly (Aggregate vs Per Stream toggle,
    # Stream Statistics table), or does mixing categories like this break
    # rendering, drop a stream, or show garbage numbers?
    page.wait_for_timeout(2000)
    per_stream_toggle = page.get_by_role("button", name="Per Stream")
    if per_stream_toggle.is_visible():
        per_stream_toggle.click()
        _buffer(page)
        stats_table = page.get_by_role("table")
        expect(stats_table).to_be_visible(timeout=15000)
        table_text = stats_table.inner_text()
        for expected in ("arp", "dns", "vxlan"):
            assert expected in table_text.lower(), (
                f"Stream Statistics table is missing a row for {expected!r} "
                f"stream once live — table text was: {table_text!r}"
            )
        assert "nan" not in table_text.lower(), (
            f"Stream Statistics table shows NaN for the cross-layer mix — "
            f"table text was: {table_text!r}"
        )

    # A hard page.goto() or go_back() here fails — this app's SPA routing
    # doesn't survive a forced reload/history nav mid-transition into the
    # live-run view. Use the SPA's own "← Dashboard" button instead.
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Wait for the run to finish naturally — never race ahead of it ---
    # Confirm Stop actually appears (traffic really started) before waiting
    # for it to go away again (traffic really finished) — checking "Stop
    # has count 0" immediately after Start is a race that can pass
    # vacuously if the button hasn't rendered yet.
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=5 * 60 * 1000)

    # --- Verify PASS before touching Deactivate/Release ---
    # The result badge displays as "PASS" (CSS text-transform: uppercase)
    # but the underlying DOM text is lowercase "pass".
    # "Reports: N" only appears once the testbed is deactivated (see project
    # bugs memory, 2026-08-28) — at this point it's still active, so the
    # same run-history page is reached via "Stats" instead.
    tile.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()
