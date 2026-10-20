"""T10 — FAIL path: genuine overload (max rate, min frame size) should
report FAIL.

Every other lifecycle test in this suite only proves the PASS path
works. None of them verify the product correctly detects and reports a
failure — a test suite that's never seen a real failure can't tell you
the failure-detection logic actually works.

Two earlier approaches were tried and ruled out (2026-08-27), both on
the assumption that a routing/addressing misconfiguration between
directly-cabled Port 3 and Port 4 would break delivery:
  1. Wrong Destination IP on both ports — still PASSed at 0.000% loss,
     1.673 Gbps Tx and Rx both.
  2. Wrong Destination MAC on both ports (the actual field a receiving
     NIC has to match) — still PASSed at 0.000% loss, 1.672 Gbps Tx and
     Rx both.
Both are real product-behavior findings, not test bugs: Rx counting
between two directly-cabled ports on this box appears to not be gated
by address-matching at all — it looks like whatever physically arrives
on the wire gets counted, regardless of whether the frame's L2/L3
addressing was "correct" for that receiver. Address-based
misconfiguration doesn't produce a FAIL on this box/topology.

This version tries a different kind of break entirely: genuine
overload. Both ports pushed to 10 Gbps (the max line rate the wizard
allows) with 64-byte frames (minimum Ethernet frame size = maximum
possible packets-per-second for a given bit rate) — the idea being that
if the appliance's own hardware/CPU can't actually sustain max PPS in
both directions at once, real frames get dropped for a real reason,
independent of any address configuration. This is actual hardware
stress, not a config trick, and unlike the address-based attempts it
carries some real risk (accepted deliberately here) of provoking
something like the Port 5-8 link-down issue seen elsewhere in this
suite — if a port drops link during this test, stop and treat it as a
hardware finding, don't retry blindly.

Everything else (Port 3+4, UDP, correct source/destination IPs and
MACs, correct subnet) matches the known-good sibling tests exactly, so
line rate and frame size are the only two variables changed from a
known-PASS config.

Stateful: generates real traffic on shared hardware, at the maximum
rate/PPS this wizard allows.

NTG 5.0 rewrite (2026-09-30): built with the shared conftest helpers and
started via Start -> "Testbed is Inactive" -> Continue. "Max line rate"
is now expressed by leaving each port's Line Rate at its default, which
5.0 defines as the port's own Max Rate ("Blank = full line rate") — on
2026-09-30 Port 4 renegotiated to 1 Gbps, so typing "10" into it would
no longer mean "max". UDP only: a 2026-09-30 email reports TCP/HTTP
64-byte streams put 5.0 in a bad state, while UDP at 64 bytes is fine.
"""
import pytest

from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED_NAME = "T10-FailPath"
# Default line rate = each port's max; 64 B frames: as hard as the box can be pushed.
SPEC = TestbedSpec(
    ports={3: PortSpec(ip="10.0.8.1", cidr=25), 4: PortSpec(ip="10.0.8.2", cidr=25)},
    streams=[StreamSpec("UDP")], frame_size=64, ramp=(2, 20, 2),
)


@pytest.mark.stateful
@pytest.mark.xfail(
    reason=(
        "Confirmed 2026-08-27: this box/topology (Port 3+4, directly "
        "cabled) doesn't produce a FAIL result via any of 3 tried "
        "mechanisms — wrong dest IP, wrong dest MAC, and this test's own "
        "max-rate/min-frame overload all still PASS at 0.000% loss. "
        "Kept as documentation of that finding, not a blocking failure. "
        "If the product/box changes such that this legitimately starts "
        "reporting FAIL, this will XPASS (not an error, strict=False) — "
        "worth noticing and updating this marker/reason at that point."
    ),
    strict=False,
)
def test_t10_fail_path_overload_max_rate_min_frame_reports_fail(traffic_engine):
    result = traffic_engine.run(TESTBED_NAME, SPEC)
    # If this reads "pass", the box sustains max rate at 64B without loss:
    # a real finding to report, not something to force. The summary sheet
    # records the measured loss either way.
    assert result.verdict == "fail", result.row_text
