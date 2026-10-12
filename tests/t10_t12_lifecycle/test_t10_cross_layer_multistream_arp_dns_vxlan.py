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

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest

from pages import PortSpec, StreamSpec, TestbedSpec
from tests.t10_t12_lifecycle.known_issues import VXLAN_START_IDLE

TESTBED_NAME = "T10-XLayer"
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.13.1", cidr=27), 4: PortSpec(rate=1, ip="10.0.13.2", cidr=27)},
    streams=[StreamSpec("ARP", frame_size=64), StreamSpec("DNS", frame_size=128),
             StreamSpec("VXLAN", frame_size=1500)],
    ramp=(4, 20, 4),
)


@pytest.mark.stateful
@VXLAN_START_IDLE
def test_t10_cross_layer_multistream_arp_dns_vxlan(traffic_engine):
    traffic_engine.run(TESTBED_NAME, SPEC).assert_passed()
