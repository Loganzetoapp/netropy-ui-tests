"""The T15 testbed: one UDP stream each way between NTG Port 3 and Port 4,
the two ports chained through WAN emulator Engine 2. Every T15 test runs
this same config, so one baseline (bypass) run serves them all
(WanBench.baseline).

500 Mbps per port: the emulator's own port 4 negotiated 1 Gbps
(netropy-ui-findings.md), so Port 4 can't carry more."""
from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED = "T15-WAN"
SPEC = TestbedSpec(
    ports={3: PortSpec(rate=500, unit="Mbps", ip="10.0.0.1", cidr=25),
           4: PortSpec(rate=500, unit="Mbps", ip="10.0.0.2", cidr=25)},
    streams=[StreamSpec("UDP")],
    frame_size=1500,
    ramp=(2, 20, 2),
)
