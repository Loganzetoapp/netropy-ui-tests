"""T10/T12 — one full lifecycle per protocol: build, start, run to the end
of its ramp, saved run PASSes, and the summary sheet's checks hold.

Replaces eight near-identical files (one per protocol) with one table. Each
case: create testbed -> ports + line rate -> optional addressing ->
streams + frame size -> ramp -> Start ("Testbed is Inactive" -> Continue)
-> wait for the saved run -> verdict pass AND frames sent/received > 0
(the NTG's own verdict is "pass" with no criteria set, so it alone proves
nothing). Teardown deactivates (freeing the ports) and deletes.

Ports (2026-10-11): .212's Ports 1/2 are 10G, Ports 3/4 are 1G (and run
through the WAN emulator's Engine 2 in bypass). Cases above 1 Gbps use 1/2.

Stateful: generates real traffic.
"""
import pytest

from pages import PortSpec, StreamSpec, TestbedSpec
from tests.t10_t12_lifecycle.known_issues import VXLAN_START_IDLE


def _pair(a, b, rate, unit, ips=None, cidr=None):
    if ips:
        return {a: PortSpec(rate=rate, unit=unit, ip=ips[0], cidr=cidr),
                b: PortSpec(rate=rate, unit=unit, ip=ips[1], cidr=cidr)}
    return {a: PortSpec(rate=rate, unit=unit), b: PortSpec(rate=rate, unit=unit)}


_VXLAN_XFAIL = VXLAN_START_IDLE

# (id, testbed name <= 15 chars, spec)
CASES = [
    pytest.param("T10-Life-UDP", TestbedSpec(
        ports=_pair(3, 4, 1, "Gbps", ("10.0.0.1", "10.0.0.2"), 25),
        streams=[StreamSpec("UDP")], frame_size=1500, ramp=(10, 50, 10)), id="udp-1gbps-1500b"),
    pytest.param("T10-Life-TCP", TestbedSpec(
        ports=_pair(1, 2, 2, "Gbps", ("10.0.1.1", "10.0.1.2"), 25),
        streams=[StreamSpec("TCP")], frame_size=512, ramp=(5, 30, 5)), id="tcp-2gbps-512b"),
    pytest.param("T10-Life-ICMP", TestbedSpec(
        ports=_pair(1, 2, 5, "Gbps", ("10.0.2.1", "10.0.2.2"), 26),
        streams=[StreamSpec("ICMP")], frame_size=64, ramp=(8, 45, 8)), id="icmp-5gbps-64b"),
    pytest.param("T10-Life-DNS", TestbedSpec(
        ports=_pair(1, 2, 200, "Mbps", ("10.0.7.1", "10.0.7.2"), 28),
        streams=[StreamSpec("DNS")], frame_size=128, ramp=(6, 35, 6)), id="dns-200mbps-128b"),
    pytest.param("T10-Life-NTP", TestbedSpec(
        ports=_pair(3, 4, 50, "Mbps", ("10.0.8.1", "10.0.8.2"), 29),
        streams=[StreamSpec("NTP")], frame_size=90, ramp=(4, 20, 4)), id="ntp-50mbps-90b"),
    pytest.param("T10-Life-ARP", TestbedSpec(
        ports=_pair(3, 4, 10, "Mbps"),
        streams=[StreamSpec("ARP")], frame_size=64, ramp=(3, 15, 3)), id="arp-10mbps-64b"),
    pytest.param("T10-Life-Multi", TestbedSpec(
        ports=_pair(1, 2, 3, "Gbps", ("10.0.6.1", "10.0.6.2"), 27),
        streams=[StreamSpec("TCP", frame_size=900), StreamSpec("ICMP", frame_size=100)],
        ramp=(5, 25, 5)), id="multistream-tcp-icmp-3gbps"),
    pytest.param("T10-Life-UT100", TestbedSpec(
        ports=_pair(3, 4, 100, "Mbps", ("10.0.4.1", "10.0.4.2"), 25),
        streams=[StreamSpec("UDP", frame_size=1500), StreamSpec("TCP", frame_size=512)],
        ramp=(5, 20, 5)), id="multistream-udp-tcp-100mbps"),
    pytest.param("T10-Life-VXLAN", TestbedSpec(
        ports=_pair(1, 2, 4, "Gbps", ("10.0.9.1", "10.0.9.2"), 27),
        streams=[StreamSpec("VXLAN")], frame_size=1500, ramp=(7, 40, 7)),
        id="vxlan-4gbps-1500b", marks=_VXLAN_XFAIL),
]


@pytest.mark.stateful
@pytest.mark.parametrize("name, spec", CASES)
def test_t10_t12_lifecycle_protocol(traffic_engine, name, spec):
    result = traffic_engine.run(name, spec)
    result.assert_passed()
