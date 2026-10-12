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

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest

from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED_NAME = "T10-AsymCIDR"
# Same /24 range, different mask widths at the two ends: /25 vs /28.
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.20.1", cidr=25), 4: PortSpec(rate=1, ip="10.0.20.2", cidr=28)},
    streams=[StreamSpec("UDP")], frame_size=1500, ramp=(10, 50, 10),
)


@pytest.mark.stateful
def test_t10_asymmetric_subnet_pairing(traffic_engine):
    traffic_engine.run(TESTBED_NAME, SPEC).assert_passed()
