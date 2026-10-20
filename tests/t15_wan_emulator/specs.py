"""The WAN bench testbed: one UDP stream each way between NTG Port 3 and
Port 4, the two ports chained through WAN emulator Engine 2. Every WAN test
(T15 delay, T16 loss, T17 bandwidth, T18 jitter) runs this same config, so
one baseline (bypass) run serves them all (WanBench.baseline). The
variants below exist only where a test needs something SPEC can't give:
a longer hold, a lower rate, or a second stream. Each gets its own
baseline.

500 Mbps per port: the emulator's own port 4 negotiated 1 Gbps
(netropy-ui-findings.md), so Port 4 can't carry more."""
from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED = "T15-WAN"
MAX_RATE_MBPS = 500


def bench_spec(rate_mbps: float = MAX_RATE_MBPS, ramp=(2, 20, 2), streams=("UDP",)) -> TestbedSpec:
    """The bench testbed at `rate_mbps` per port (Kbps below 1 Mbps, whole
    numbers only: the line-rate box takes what it's given)."""
    rate, unit = (round(rate_mbps * 1000), "Kbps") if rate_mbps < 1 else (round(rate_mbps, 3), "Mbps")
    if float(rate).is_integer():
        rate = int(rate)   # the box shows 250, not 250.0
    return TestbedSpec(
        ports={3: PortSpec(rate=rate, unit=unit, ip="10.0.0.1", cidr=25),
               4: PortSpec(rate=rate, unit=unit, ip="10.0.0.2", cidr=25)},
        streams=[StreamSpec(protocol) for protocol in streams],
        frame_size=1500,
        ramp=ramp,
    )


SPEC = bench_spec()
# T19a outage / T19b change mid-run: 40 s of steady state, room for four
# outage cycles, or a clean stretch either side of an edit.
LONG_SPEC = bench_spec(ramp=(2, 40, 2))
# T19c long delay: 100 Mbps keeps a 2 s delay's 25 MB per direction in
# flight well inside the emulator's buffers; a short hold makes the delay
# long against the run.
SLOW_SPEC = bench_spec(rate_mbps=100, ramp=(1, 8, 1))
# T21 per-stream paths: a UDP and a TCP stream, which the emulator's
# endpoints tell apart by protocol. The NTG splits each port's rate
# evenly between them.
TWO_STREAM_SPEC = bench_spec(streams=("UDP", "TCP"))


def preset_rate_mbps(path) -> float:
    """An offered rate safely under a preset's tightest cap (half of it),
    so a preset test measures delay and loss, not a full queue."""
    cap = path.min_cap_mbps
    return MAX_RATE_MBPS if cap is None else min(MAX_RATE_MBPS, cap / 2)
