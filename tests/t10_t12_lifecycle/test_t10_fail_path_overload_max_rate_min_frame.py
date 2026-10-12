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
from playwright.sync_api import Page

from conftest import (
    add_stream,
    assert_activatable_name,
    create_testbed,
    enable_ports,
    open_editor,
    remove_testbed,
    run_verdict,
    set_addressing,
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-FailPath"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


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
def test_t10_fail_path_overload_max_rate_min_frame_reports_fail(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)
    enable_ports(page, PORTS)  # default Line Rate = each port's max
    set_addressing(page, (3, 4), ("10.0.8.1", "10.0.8.2"), cidr=25)
    add_stream(page, "UDP")
    set_all_frame_sizes(page, 64)
    set_ramp(page, up=2, hold=20, down=2)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=24_000 + 3 * 60_000)

    # If this reads "pass", the box sustains max rate at 64B without loss —
    # a real finding to report, not something to force.
    assert run_verdict(run) == "fail"
