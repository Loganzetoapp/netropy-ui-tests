"""T14 investigation — is a "lost run" caused by a frame too small for the
protocol's own headers?

Found 2026-10-01 on NTG 5.0.7b (.89): some runs look live, then fall back
to "Ports are armed and idle" with no saved run and no error (stats
lost) — NTP @ 90 B (5/5), DNS @ 64 B (2/2), UDP/IPv6 @ 64 B (1/1) — while
UDP, ICMP and ARP @ 64 B save fine. Every lost case is a frame smaller
than its protocol's headers plus the 4-byte FCS:

    UDP/IPv6  14 Eth + 40 IPv6 + 8 UDP + 4 FCS            = 66 B  > 64
    NTP       14 Eth + 20 IPv4 + 8 UDP + 48 NTP + 4 FCS   = 94 B  > 90
    DNS       14 Eth + 20 IPv4 + 8 UDP + 12 DNS hdr + query + 4 > 64

and every saved case fits (UDP/ICMP/ARP need ~46 B). The editor accepts
any frame size without validation (see T7 frame-size-bounds tests).

Hypothesis — CONFIRMED 2026-10-01 for every protocol tried: a frame
smaller than the stream's real header size makes the run die silently.
TCP's real minimum turned out to be 70 B (its header carries 12 B of
options), which is why TCP @ 64 B is lost although a bare TCP header
would fit. Each case below pairs one of those protocols with a size
just below and comfortably above its header minimum, on the same ports,
rate and ramp as the 64-byte sweep. If the small size loses the run and
the larger one saves, the hypothesis holds; if both save or both lose,
it doesn't.

A lost run raises SystemBadStateError (reported as a system failure).
These are investigation cases, not pass/fail product requirements: the
"too small" ones are expected to lose the run until the product either
rejects the size or handles it.

Stateful: generates real traffic.
"""
import pytest
from playwright.sync_api import Page

from pages import PortSpec, StreamSpec, TestbedSpec, UnitHealth

# (picker label, testbed name, frame bytes, header minimum incl. FCS)
CASES = [
    ("UDP (IPv6)", "T14-Sz-UDP6-64", 64, 66),
    ("UDP (IPv6)", "T14-Sz-UDP6-128", 128, 66),
    ("NTP", "T14-Sz-NTP-90", 90, 94),
    ("NTP", "T14-Sz-NTP-128", 128, 94),
    ("DNS", "T14-Sz-DNS-64", 64, 70),
    ("DNS", "T14-Sz-DNS-256", 256, 70),
    # TCP: the basic header would fit 64 B (14 + 20 + 20 + 4 = 58), but the
    # stream's TCP header carries 12 B of options (32 B total), so its real
    # minimum is 14 + 20 + 32 + 4 = 70 B. Measured 2026-10-01: 64/66/68 B
    # lose the run, 70/72/80/96/128 B pass.
    ("TCP", "T14-Sz-TCP-66", 66, 70),
    ("TCP", "T14-Sz-TCP-68", 68, 70),
    ("TCP", "T14-Sz-TCP-70", 70, 70),
    ("TCP", "T14-Sz-TCP-72", 72, 70),
    ("TCP", "T14-Sz-TCP-80", 80, 70),
    ("TCP", "T14-Sz-TCP-96", 96, 70),
    ("TCP", "T14-Sz-TCP-128", 128, 70),
    ("TCP (IPv6)", "T14-Sz-TCP6-128", 128, 90),
    ("HTTP", "T14-Sz-HTTP-256", 256, 70),
    ("HTTP", "T14-Sz-HTTP1500", 1500, 70),
]


@pytest.mark.stateful
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[f"{p.replace(' (', '-').rstrip(')')}-{size}B" for p, _, size, _ in CASES],
)
def test_t14_frame_size_vs_protocol_headers(dashboard: Page, traffic_engine, case):
    protocol, name, size, header_min = case
    health = UnitHealth(dashboard)
    print(f"[T14 size] {protocol} @ {size} B: header minimum ~{header_min} B, fits: {size >= header_min}")
    spec = TestbedSpec(ports={3: PortSpec(rate=500, unit="Mbps"), 4: PortSpec(rate=500, unit="Mbps")},
                       streams=[StreamSpec(protocol)], frame_size=size, ramp=(2, 15, 2))

    health.assert_healthy(context=f"before {protocol} @ {size} B")
    result = traffic_engine.run(name, spec)
    print(f"[T14 size] {protocol} @ {size} B saved run: {result.row_text!r}")
    health.assert_healthy(context=f"after {protocol} @ {size} B", testbed=name)
    result.assert_passed()
